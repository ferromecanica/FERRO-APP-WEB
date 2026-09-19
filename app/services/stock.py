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


def modificar_consumo(consumo, cantidad, precio_unitario, descripcion=None, precio_costo=None):
    """Edita un renglón de la OT. Si cambia la cantidad, ajusta el stock por la diferencia."""
    diferencia = cantidad - consumo.cantidad
    if diferencia:
        registrar_movimiento(
            consumo.repuesto, -diferencia, "Consumo" if diferencia > 0 else "Reversion",
            detalle=f"Corrección de cantidad: {consumo.descripcion}", ot_id=consumo.ot_id,
        )
    consumo.cantidad = cantidad
    consumo.precio_unitario = precio_unitario
    if descripcion:
        consumo.descripcion = descripcion
    if precio_costo is not None:
        consumo.precio_costo = precio_costo


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
            item.repuesto.costo_lista = item.costo_unitario
            recalcular_precio_venta(item.repuesto)
    ingreso.estado = "Confirmado"


def anular_ingreso(ingreso):
    """Deshace una compra confirmada: saca del stock lo que había sumado (los costos quedan como están)."""
    if ingreso.estado != "Confirmado":
        raise ValueError("Solo se puede anular un ingreso confirmado.")
    for item in ingreso.items:
        registrar_movimiento(
            item.repuesto, -item.cantidad, "Reversion",
            detalle=f"Anulación de ingreso {ingreso.nro_factura or ingreso.id}", ingreso_id=ingreso.id,
        )
    ingreso.estado = "Anulado"


def clave_markup(repuesto):
    """Clave para buscar la regla del proveedor (como en AppSheet).

    FGC Lubes: el envase (los de 204 L o más cuentan como "204"). Resto: Marca_RSF o, si está vacía, la marca.
    """
    clave = (repuesto.marca_proveedor or repuesto.marca or "").strip()
    if repuesto.proveedor == "FGC Lubes":
        try:
            litros = float(clave.replace(",", "."))
            clave = "204" if litros >= 204 else f"{litros:g}"
        except ValueError:
            pass
    return clave or None


def regla_markup(repuesto):
    """(markup, de dónde sale). Mismo orden que la fórmula de AppSheet:
    1) proveedor + clave  2) proveedor general  3) markup propio del repuesto  4) 1,0."""
    if repuesto.proveedor:
        clave = clave_markup(repuesto)
        if clave:
            regla = ConfigMarkup.query.filter(ConfigMarkup.proveedor == repuesto.proveedor,
                                              db.func.trim(ConfigMarkup.marca_envase) == clave).first()
            if regla:
                return regla.markup, f"{repuesto.proveedor} + {clave}"
        regla = ConfigMarkup.query.filter_by(proveedor=repuesto.proveedor, marca_envase=None).first()
        if regla:
            return regla.markup, f"{repuesto.proveedor} (general)"
    if repuesto.markup:
        return repuesto.markup, "propio del repuesto"
    return 1.0, "sin regla de markup"


def markup_para(repuesto):
    """Markup propio del repuesto o, si no tiene, el configurado para proveedor + marca."""
    return regla_markup(repuesto)[0]


def recalcular_precio_venta(repuesto):
    """Costo final = costo de lista × (1 − descuento); venta = costo final × markup (como en AppSheet)."""
    costo = (repuesto.costo_lista or 0) * (1 - (repuesto.descuento_oferta or 0))
    repuesto.precio_costo = round(costo, 2)
    repuesto.precio_venta = round(costo * markup_para(repuesto), 2)
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
