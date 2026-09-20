"""Actualización masiva de precios con la lista que manda el proveedor.

El archivo del proveedor (Excel o CSV) trae una fila por artículo. Ferro no sabe
cómo se llaman sus columnas, así que se las elige a mano una vez por proveedor
(PerfilLista) y de ahí en más vienen puestas.

El costo de lista sale de:  precio del archivo ÷ envase × factor
y el precio de venta se recalcula con el markup de siempre.
"""
import csv
import io
import re

from ..extensions import db
from ..models import Repuesto
from ..validaciones import numero_ar
from .stock import recalcular_precio_venta

CAMPOS_CODIGO = {
    "nro_parte": "Nº de parte",
    "cod_proveedor": "Código de proveedor",
    "codigo_barras": "Código de barras",
}
MAX_FILAS = 20000


class ErrorLista(Exception):
    pass


def _normalizar(valor):
    """Para comparar códigos: sin espacios, guiones ni mayúsculas."""
    return re.sub(r"[^A-Z0-9]", "", str(valor or "").upper())


def leer(datos, nombre):
    """Devuelve (columnas, filas) del archivo subido. Cada fila es un dict columna → valor."""
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        filas = _leer_excel(datos)
    elif nombre.lower().endswith((".csv", ".txt")):
        filas = _leer_csv(datos)
    else:
        raise ErrorLista("El archivo tiene que ser Excel (.xlsx) o CSV. Si te lo mandan en PDF, "
                         "abrilo con Excel y guardalo como .xlsx.")
    if not filas:
        raise ErrorLista("No encontré filas con datos en el archivo.")
    return list(filas[0].keys()), filas


def _titulos(valores):
    """Nombres de las columnas, rellenando las que vienen vacías."""
    titulos, vistos = [], set()
    for i, v in enumerate(valores):
        titulo = str(v).strip() if v not in (None, "") else f"Columna {i + 1}"
        while titulo in vistos:  # dos columnas con el mismo nombre
            titulo += " "
        vistos.add(titulo)
        titulos.append(titulo)
    return titulos


def _fila_de_titulos(filas):
    """La primera fila con al menos dos celdas con texto: arriba suele haber logos y títulos."""
    for i, fila in enumerate(filas):
        if sum(1 for v in fila if str(v or "").strip()) >= 2:
            return i
    return 0


def _leer_excel(datos):
    import openpyxl

    libro = openpyxl.load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
    hoja = libro[libro.sheetnames[0]]
    crudas = [list(f) for f in hoja.iter_rows(max_row=MAX_FILAS, values_only=True)]
    libro.close()
    return _armar(crudas)


def _leer_csv(datos):
    texto = datos.decode("utf-8-sig", errors="replace")
    muestra = texto[:4000]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t|")
    except csv.Error:
        dialecto = csv.excel
        dialecto.delimiter = ";" if muestra.count(";") > muestra.count(",") else ","
    return _armar([f for f in csv.reader(io.StringIO(texto), dialecto)][:MAX_FILAS])


def _armar(crudas):
    if not crudas:
        return []
    inicio = _fila_de_titulos(crudas)
    titulos = _titulos(crudas[inicio])
    filas = []
    for cruda in crudas[inicio + 1:]:
        if not any(str(v or "").strip() for v in cruda):
            continue
        filas.append({t: (cruda[i] if i < len(cruda) else None) for i, t in enumerate(titulos)})
    return filas


def _numero(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    return numero_ar(str(valor or ""))


def equivalencias(texto):
    """'16=4, 20=20' → {16.0: 4.0, 20.0: 20.0} (envases que se cuentan distinto)."""
    tabla = {}
    for parte in re.split(r"[,;]", texto or ""):
        if "=" in parte:
            de, a = parte.split("=", 1)
            de, a = _numero(de), _numero(a)
            if de and a:
                tabla[de] = a
    return tabla


def _costo(fila, perfil):
    """Costo de lista de una fila del archivo, o None si no se puede calcular."""
    precio = _numero(fila.get(perfil["col_precio"]))
    if not precio:
        return None
    if perfil.get("col_envase"):
        envase = _numero(fila.get(perfil["col_envase"])) or 1
        envase = equivalencias(perfil.get("equivalencias")).get(envase, envase)
        if envase:
            precio /= envase
    return round(precio * (perfil.get("factor") or 1), 2)


def previsualizar(filas, perfil):
    """Qué pasaría si se aplicara la lista: (cambios, sin_cambio, no_encontrados, sobrantes).

    - cambios: repuestos del proveedor cuyo costo cambia (con el costo y la venta nuevos)
    - sin_cambio: los que quedan igual
    - no_encontrados: repuestos del proveedor que no están en el archivo
    - sobrantes: filas del archivo que no corresponden a ningún repuesto nuestro
    """
    campo = perfil.get("campo_codigo") or "nro_parte"
    del_archivo = {}
    for fila in filas:
        clave = (_normalizar(fila.get(perfil["col_codigo"])),
                 _normalizar(fila.get(perfil["col_marca"])) if perfil.get("col_marca") else "")
        if clave[0]:
            del_archivo.setdefault(clave, fila)

    cambios, sin_cambio, no_encontrados, usadas = [], [], [], set()
    repuestos = Repuesto.query.filter(Repuesto.proveedor == perfil["proveedor"],
                                      Repuesto.id != Repuesto.ID_VARIOS).order_by(Repuesto.nombre).all()
    for r in repuestos:
        clave = (_normalizar(getattr(r, campo, None)),
                 _normalizar(r.marca_proveedor or r.marca) if perfil.get("col_marca") else "")
        fila = del_archivo.get(clave)
        if fila is None and perfil.get("col_marca"):  # el código solo, si la marca no coincide
            candidatas = [k for k in del_archivo if k[0] == clave[0]]
            fila = del_archivo[candidatas[0]] if len(candidatas) == 1 else None
            clave = candidatas[0] if fila is not None else clave
        if fila is None:
            no_encontrados.append(r)
            continue
        usadas.add(clave)
        costo = _costo(fila, perfil)
        if costo is None:
            no_encontrados.append(r)
            continue
        viejo = r.costo_lista or 0
        dato = {"repuesto": r, "costo_viejo": viejo, "costo_nuevo": costo,
                "variacion": (costo - viejo) / viejo * 100 if viejo else None,
                "venta_nueva": _venta_con(r, costo)}
        (sin_cambio if abs(costo - viejo) < 0.01 else cambios).append(dato)

    sobrantes = sum(1 for k in del_archivo if k not in usadas)
    cambios.sort(key=lambda d: abs(d["variacion"] or 0), reverse=True)
    return cambios, sin_cambio, no_encontrados, sobrantes


def _venta_con(repuesto, costo):
    """Precio de venta que quedaría, sin tocar el repuesto."""
    viejo = repuesto.costo_lista
    repuesto.costo_lista = costo
    try:
        costo_final = (costo or 0) * (1 - (repuesto.descuento_oferta or 0))
        from .stock import markup_para

        return round(costo_final * markup_para(repuesto), 2)
    finally:
        repuesto.costo_lista = viejo


def aplicar(cambios):
    """Guarda los costos nuevos y recalcula los precios de venta. No hace commit."""
    for dato in cambios:
        dato["repuesto"].costo_lista = dato["costo_nuevo"]
        recalcular_precio_venta(dato["repuesto"])
    db.session.flush()
    return len(cambios)
