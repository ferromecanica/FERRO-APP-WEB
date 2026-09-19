"""Reglas de stock: todo cambio de stock pasa por acá y deja un MovimientoStock.

Las funciones no hacen commit: el que llama decide cuándo confirmar la
transacción, así una OT con varios consumos entra entera o no entra.
"""
from flask_login import current_user

from ..extensions import db
from ..models import ConfigMarkup, ConsumoOT, MovimientoStock, Repuesto


def _usuario_id():
    return current_user.id if current_user and current_user.is_authenticated else None


def registrar_movimiento(repuesto, cantidad, tipo, detalle=None, ot_id=None, venta_id=None, ingreso_id=None):
    """Aplica `cantidad` (con signo) al stock del repuesto y registra el movimiento."""
    if repuesto.controla_stock:
        repuesto.stock_actual = (repuesto.stock_actual or 0) + cantidad
    mov = MovimientoStock(
        repuesto=repuesto,
        cantidad=cantidad,
        tipo=tipo,
        detalle=detalle or repuesto.nombre,
        ot_id=ot_id,
        venta_id=venta_id,
        ingreso_id=ingreso_id,
        usuario_id=_usuario_id(),
    )
    db.session.add(mov)
    return mov


def consumir_en_ot(ot, repuesto, cantidad, precio_unitario=None, descripcion=None, precio_costo=None):
    """Agrega un consumo a la OT y descuenta stock. Congela precio de venta y costo."""
    consumo = ConsumoOT(
        ot=ot,
        repuesto=repuesto,
        cantidad=cantidad,
        precio_unitario=repuesto.precio_venta if precio_unitario is None else precio_unitario,
        precio_costo=(repuesto.precio_costo or 0) if precio_costo is None else precio_costo,
        descripcion=descripcion or repuesto.nombre,
    )
    db.session.add(consumo)
    registrar_movimiento(repuesto, -cantidad, "Consumo", detalle=consumo.descripcion, ot_id=ot.id)
    return consumo


def revertir_consumo(consumo):
    """Devuelve al stock lo consumido y elimina el renglón de la OT."""
    registrar_movimiento(
        consumo.repuesto,
        consumo.cantidad,
        "Reversion",
        detalle=f"Reversión: {consumo.descripcion}",
        ot_id=consumo.ot_id,
    )
    db.session.delete(consumo)


def confirmar_ingreso(ingreso):
    """Suma al stock todos los ítems de una compra y actualiza costos."""
    if ingreso.estado == "Confirmado":
        raise ValueError("El ingreso ya estaba confirmado.")
    for item in ingreso.items:
        registrar_movimiento(
            item.repuesto,
            item.cantidad,
            "Ingreso",
            detalle=f"{ingreso.proveedor} {ingreso.nro_factura or ''}".strip(),
            ingreso_id=ingreso.id,
        )
        if item.costo_unitario and not item.repuesto.costo_manual:
            item.repuesto.precio_costo = item.costo_unitario
            recalcular_precio_venta(item.repuesto)
    ingreso.estado = "Confirmado"


def markup_para(repuesto):
    """Markup propio del repuesto o, si no tiene, el configurado para proveedor + marca."""
    if repuesto.markup:
        return repuesto.markup
    regla = (
        ConfigMarkup.query.filter_by(proveedor=repuesto.proveedor, marca_envase=repuesto.marca_proveedor).first()
        or ConfigMarkup.query.filter_by(proveedor=repuesto.proveedor, marca_envase=None).first()
    )
    return regla.markup if regla else 1.0


def recalcular_precio_venta(repuesto):
    precio = (repuesto.precio_costo or 0) * markup_para(repuesto)
    if repuesto.descuento_oferta:
        precio *= 1 - repuesto.descuento_oferta
    repuesto.precio_venta = round(precio, 2)
    return repuesto.precio_venta


def repuesto_varios():
    """El ítem genérico 'Varios / Mano de Obra' (id 99): se crea si no existe."""
    varios = db.session.get(Repuesto, Repuesto.ID_VARIOS)
    if varios is None:
        varios = Repuesto(id=Repuesto.ID_VARIOS, nombre="Varios / Mano de Obra", marca="N/A")
        db.session.add(varios)
        db.session.flush()
    return varios


def buscar_repuesto(codigo):
    """Busca por código de barras, nro de parte o ID (para el scanner)."""
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    rep = Repuesto.query.filter(
        (Repuesto.codigo_barras == codigo) | (Repuesto.nro_parte == codigo)
    ).first()
    if rep is None and codigo.isdigit():
        rep = db.session.get(Repuesto, int(codigo))
    return rep
