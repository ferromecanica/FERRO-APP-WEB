"""Importa datos del Excel de AppSheet (Taller_Mec.xlsx) a la base de Ferro.

Uso:  python scripts/importar_appsheet.py <ruta al .xlsx> repuestos   (repuestos, proveedores, markups)
      python scripts/importar_appsheet.py <ruta al .xlsx> clientes    (clientes y vehículos)

Se puede correr varias veces: actualiza por número de repuesto (no duplica).
Hace una copia de la base antes de tocar nada.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import openpyxl  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    Categoria, Cliente, ConfigMarkup, MovimientoStock, Proveedor, Repuesto, Subcategoria, Vehiculo,
)
from app.validaciones import cuit_valido, formatear_cuit, normalizar_patente  # noqa: E402
from app.services.backup import hacer_copia  # noqa: E402


def filas(libro, hoja):
    it = libro[hoja].iter_rows(values_only=True)
    encabezado = next(it)
    return [dict(zip(encabezado, r)) for r in it if r and r[0] is not None]


def texto(valor):
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    t = str(valor).strip()
    return t or None


def asegurar_proveedor(nombre):
    if nombre and not Proveedor.query.filter(func.lower(Proveedor.nombre) == nombre.lower()).first():
        db.session.add(Proveedor(nombre=nombre))


def importar_repuestos(libro):
    cats = {c.nombre.upper(): c for c in Categoria.query.all()}
    subs = {(s.categoria.nombre.upper(), s.nombre.upper()): s for s in Subcategoria.query.all()}
    nuevos = actualizados = 0
    for r in filas(libro, "Repuestos"):
        rid = int(r["ID_Repuesto"])
        if rid == Repuesto.ID_VARIOS:
            continue
        cat_nombre = (texto(r["Categoria"]) or "").upper()
        sub_nombre = (texto(r["Sub_categoria"]) or "").upper()
        if cat_nombre and cat_nombre not in cats:
            cats[cat_nombre] = Categoria(nombre=cat_nombre)
            db.session.add(cats[cat_nombre])
        if cat_nombre and sub_nombre and (cat_nombre, sub_nombre) not in subs:
            subs[(cat_nombre, sub_nombre)] = Subcategoria(nombre=sub_nombre, categoria=cats[cat_nombre])
            db.session.add(subs[(cat_nombre, sub_nombre)])
        proveedor = texto(r["Proveedor"])
        asegurar_proveedor(proveedor)

        descuento = r["Descuento_Oferta"] or None
        costo = float(r["Precio_Costo"] or 0)
        rep = db.session.get(Repuesto, rid)
        if rep is None:
            rep = Repuesto(id=rid, stock_actual=0)
            db.session.add(rep)
            nuevos += 1
        else:
            actualizados += 1
        rep.nombre = texto(r["Nombre"]) or f"Repuesto {rid}"
        rep.proveedor = proveedor
        rep.marca = texto(r["Marca"])
        rep.nro_parte = texto(r["Nro_Parte"])
        rep.codigo_barras = texto(r["Codigo_Barras"])
        rep.cod_proveedor = texto(r["Cod_Proveedor"])
        rep.marca_proveedor = texto(r["Marca_RSF"])
        rep.categoria = cats.get(cat_nombre)
        rep.subcategoria = subs.get((cat_nombre, sub_nombre))
        rep.costo_lista = round(costo / (1 - descuento), 2) if descuento and descuento < 1 else costo
        rep.descuento_oferta = descuento
        rep.precio_costo = costo
        rep.costo_manual = r["Costo_Manual"] is not None
        rep.markup = r["Markup"] or None
        rep.precio_venta = float(r["Precio_Venta"] or 0)  # tal cual AppSheet (no se recalcula)
        rep.comp_marca = texto(r["Comp_Auto_Marca"])
        rep.comp_modelo = texto(r["Comp_Auto_Modelo"])
        rep.comp_motor = texto(r["Comp_Auto_Motor"])
        rep.detalle = texto(r["Detalle"])

        stock = float(r["Stock_Actual"] or 0)
        diferencia = stock - (rep.stock_actual or 0)
        if diferencia:
            rep.stock_actual = stock
            db.session.flush()
            db.session.add(MovimientoStock(repuesto_id=rid, cantidad=diferencia, tipo="Ajuste",
                                           detalle="Stock importado de AppSheet"))
    return nuevos, actualizados


def importar_markups(libro):
    ConfigMarkup.query.delete()
    for m in filas(libro, "Config_Markups"):
        proveedor = texto(m["Proveedor"])
        asegurar_proveedor(proveedor)
        db.session.add(ConfigMarkup(proveedor=proveedor, marca_envase=texto(m["Marca_Envase"]), markup=m["Markup"]))
    return ConfigMarkup.query.count()


def id_cliente(codigo):
    """'CLI-003' → 3 (el número de cliente se conserva)."""
    t = texto(codigo) or ""
    return int(t.split("-")[-1]) if t.split("-")[-1].isdigit() else None


def importar_clientes(libro):
    nuevos = actualizados = 0
    for c in filas(libro, "Clientes"):
        cid = id_cliente(c["ID_Cliente"])
        if cid is None:
            continue
        cli = db.session.get(Cliente, cid)
        if cli is None:
            cli = Cliente(id=cid)
            db.session.add(cli)
            nuevos += 1
        else:
            actualizados += 1
        cli.nombre = texto(c["Nombre_Completo"]) or f"Cliente {cid}"
        cli.telefono = texto(c["Telefono"])
        cli.email = (texto(c["Email"]) or "").lower() or None
        cli.direccion = texto(c["Direccion"])
        cli.notas = texto(c["Notas"])
        cuit = texto(c["CUIT"])
        cli.cuit = formatear_cuit(cuit) if cuit and cuit_valido(cuit) else cuit
        cli.condicion_iva = texto(c["Condicion_IVA"]) or "Consumidor Final"
    return nuevos, actualizados


def importar_vehiculos(libro):
    nuevos = actualizados = 0
    for v in filas(libro, "Vehiculos"):
        patente = normalizar_patente(texto(v["ID_Patente"]))
        if not patente:
            continue
        veh = Vehiculo.query.filter_by(patente=patente).first()
        if veh is None:
            veh = Vehiculo(patente=patente)
            db.session.add(veh)
            nuevos += 1
        else:
            actualizados += 1
        cid = id_cliente(v["ID_Cliente"])
        veh.cliente_id = cid if cid and db.session.get(Cliente, cid) else None
        veh.marca, veh.modelo, veh.motor = texto(v["Marca"]), texto(v["Modelo"]), texto(v["Motor"])
        veh.traccion, veh.color = texto(v["Tracción"]), texto(v["Color"])
        veh.vin, veh.ecu_marca, veh.ecu_modelo = texto(v["VIN"]), texto(v["ECU_Marca"]), texto(v["ECU_Modelo"])
        anio, km = v["Año"], v["Kilometraje"]
        veh.anio = int(anio) if isinstance(anio, (int, float)) else None
        veh.kilometraje = int(km) if isinstance(km, (int, float)) else None
        db.session.flush()
    return nuevos, actualizados


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[2] not in ("repuestos", "clientes"):
        sys.exit(__doc__)
    libro = openpyxl.load_workbook(sys.argv[1], data_only=True, read_only=True)
    app = create_app()
    with app.app_context():
        print("Copia de seguridad:", hacer_copia(app.config["SQLALCHEMY_DATABASE_URI"]).name)
        if sys.argv[2] == "clientes":
            c_n, c_a = importar_clientes(libro)
            db.session.flush()
            v_n, v_a = importar_vehiculos(libro)
            db.session.commit()
            sin_dueno = Vehiculo.query.filter(Vehiculo.cliente_id.is_(None)).count()
            print(f"✓ Clientes: {c_n} nuevos, {c_a} actualizados · Vehículos: {v_n} nuevos, {v_a} actualizados"
                  f" ({sin_dueno} sin dueño)")
            sys.exit(0)
        nuevos, actualizados = importar_repuestos(libro)
        reglas = importar_markups(libro)
        db.session.commit()
        print(f"✓ Repuestos: {nuevos} nuevos, {actualizados} actualizados · reglas de markup: {reglas}")
        print(f"  Total en la base: {Repuesto.query.filter(Repuesto.id != Repuesto.ID_VARIOS).count()} repuestos, "
              f"{Proveedor.query.count()} proveedores")
