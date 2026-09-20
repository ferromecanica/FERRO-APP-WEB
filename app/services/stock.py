"""Reglas de stock: todo cambio de stock pasa por acá y deja un MovimientoStock.

Las funciones no hacen commit: el que llama decide cuándo confirmar la
transacción, así una OT con varios consumos entra entera o no entra.
"""
import re
from difflib import SequenceMatcher

from flask_login import current_user

from ..extensions import db
from ..models import ConfigMarkup, ConsumoOT, MovimientoStock, Repuesto, VentaItem


def _usuario_id():
    return current_user.id if current_user and current_user.is_authenticated else None


# ─────────────────────── Control de repuestos repetidos ─────────────────────

CAMPOS_CLAVE = [
    ("nro_parte", "el mismo nº de parte"),
    ("cod_proveedor", "el mismo código de proveedor"),
    ("codigo_barras", "el mismo código de barras"),
]


def _normalizar(valor):
    """Para comparar: sin espacios, guiones ni mayúsculas ('318 105' y '318-105' son lo mismo)."""
    return re.sub(r"[^A-Z0-9]", "", (valor or "").upper())


def _distancia(a, b):
    """Cuántos caracteres hay que cambiar para pasar de a a b (corta en 2: solo interesa 0 o 1)."""
    if abs(len(a) - len(b)) > 1:
        return 2
    cambios = sum(1 for x, y in zip(a, b) if x != y) if len(a) == len(b) else 1
    if len(a) != len(b):  # uno tiene un carácter de más: ¿el resto coincide?
        largo, corto = (a, b) if len(a) > len(b) else (b, a)
        if not any(largo[:i] + largo[i + 1:] == corto for i in range(len(largo))):
            return 2
    return min(cambios, 2)


def _misma_marca(a, b):
    """Dos repuestos son 'de la misma marca' si coinciden o si a alguno le falta la marca."""
    ma, mb = _normalizar(a.marca), _normalizar(b.marca)
    return not ma or not mb or ma == mb


def _palabras(nombre):
    return [p for p in re.split(r"[^A-Z0-9]+", (nombre or "").upper()) if p]


def _mismo_nombre(a, b):
    """True si los nombres son el mismo producto: mismas palabras, salvo algún error de tipeo.

    'KIT47 FILTROS MAHLE' y 'KIT47 HAB FILTROS MAHLE' son distintos (HAB cambia el producto);
    'AMORTIGUADOR' y 'AMORTIGADOR' son el mismo (una letra de diferencia en una palabra larga).
    """
    pa, pb = set(_palabras(a)), set(_palabras(b))
    if not pa or not pb:
        return False
    if pa == pb:
        return True
    sueltas_a, sueltas_b = sorted(pa - pb), sorted(pb - pa)
    if len(sueltas_a) != len(sueltas_b) or len(sueltas_a) > 2:
        return False  # a una le sobra una palabra (HAB, 4L…): es otro producto
    # cada palabra distinta tiene que ser la misma con un error de tipeo (y ser larga)
    return all(len(x) >= 4 and len(y) >= 4 and _distancia(x, y) == 1 for x, y in zip(sueltas_a, sueltas_b))


def posibles_duplicados(repuesto):
    """Repuestos ya cargados que probablemente sean el mismo. Devuelve [(repuesto, motivo)].

    Avisa cuando: comparten código de barras; comparten nº de parte o de proveedor **y** la marca;
    o el nombre es casi idéntico. Un nº de parte parecido (una letra o número de diferencia) solo
    cuenta si además el nombre casi coincide: los kits KIT01, KIT02… son distintos entre sí.
    """
    otros = Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS)
    if repuesto.id:
        otros = otros.filter(Repuesto.id != repuesto.id)
    barras = _normalizar(repuesto.codigo_barras)
    encontrados = {}
    for otro in otros.all():
        motivo = None
        mismo_nombre = _mismo_nombre(repuesto.nombre, otro.nombre)
        if len(barras) >= 6 and barras == _normalizar(otro.codigo_barras):
            motivo = "el mismo código de barras"
        else:
            for campo, texto in (("nro_parte", "el mismo nº de parte"), ("cod_proveedor", "el mismo código de proveedor")):
                mio, suyo = _normalizar(getattr(repuesto, campo)), _normalizar(getattr(otro, campo))
                if len(mio) < 3 or len(suyo) < 3:
                    continue
                if mio == suyo and _misma_marca(repuesto, otro):
                    motivo = motivo or f"{texto} y la misma marca"
                elif _distancia(mio, suyo) == 1 and mismo_nombre and _misma_marca(repuesto, otro):
                    motivo = motivo or f"un {texto.replace('el mismo ', '')} muy parecido y un nombre casi igual"
            if not motivo and mismo_nombre and len(_palabras(repuesto.nombre)) >= 2:
                motivo = "el mismo nombre" + ("" if _normalizar(repuesto.nombre) == _normalizar(otro.nombre) else " (con alguna letra distinta)")
        if motivo:
            encontrados[otro.id] = (otro, motivo)
    return list(encontrados.values())


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


def vender_en_mostrador(venta, repuesto, cantidad, precio_unitario=None, descripcion=None, costo_unitario=None):
    """Agrega un renglón a una venta de mostrador y descuenta stock.

    Igual que el consumo en una OT, pero sin OT: el mostrador vende directo.
    """
    item = VentaItem(
        venta=venta,
        repuesto=repuesto,
        cantidad=cantidad,
        precio_unitario=(repuesto.precio_venta or 0) if precio_unitario is None else precio_unitario,
        costo_unitario=(repuesto.precio_costo or 0) if costo_unitario is None else costo_unitario,
        descripcion=descripcion or (repuesto.nombre if repuesto else ""),
    )
    db.session.add(item)
    if repuesto is not None:
        db.session.flush()  # la venta necesita id para el movimiento
        registrar_movimiento(repuesto, -cantidad, "Venta", detalle=item.descripcion, venta_id=venta.id)
    return item


def anular_venta(venta):
    """Deshace una venta de mostrador: lo que salió del stock vuelve."""
    if venta.ot_id:
        raise ValueError("Esta venta salió de una OT: se maneja desde la OT.")
    for item in venta.items:
        if item.repuesto_id:
            registrar_movimiento(
                item.repuesto, item.cantidad, "Reversion",
                detalle=f"Anulación de la venta {venta.id}: {item.descripcion}", venta_id=venta.id,
            )


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
