"""Actualización masiva de precios con la lista que manda el proveedor.

El archivo del proveedor (Excel, CSV, TXT o PDF) trae una fila por artículo.
Ferro no sabe cómo se llaman sus columnas, así que se las elige a mano una vez
por proveedor (PerfilLista) y de ahí en más vienen puestas.

El costo de lista sale de:  precio del archivo ÷ envase × factor
y el precio de venta se recalcula con el markup de siempre.

Las listas son grandes (la de RSF tiene 119.000 filas), así que el archivo se
recorre de a una fila y solo se guardan en memoria las que nos sirven.
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
EXTENSIONES = (".xlsx", ".xlsm", ".csv", ".txt", ".pdf")
MAX_FILAS = 300000


class ErrorLista(Exception):
    pass


def _normalizar(valor):
    """Para comparar códigos: sin espacios, guiones ni mayúsculas."""
    return re.sub(r"[^A-Z0-9]", "", str(valor or "").upper())


def _numero(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    return numero_ar(str(valor or ""))


# ──────────────────────────── Lectura del archivo ───────────────────────────


def abrir(ruta, nombre=None):
    """(columnas, filas). Las filas son listas y vienen de a una: el archivo puede ser enorme."""
    nombre = (nombre or str(ruta)).lower()
    if nombre.endswith((".xlsx", ".xlsm")):
        return _abrir_excel(ruta)
    if nombre.endswith(".pdf"):
        return _abrir_pdf(ruta)
    if nombre.endswith((".csv", ".txt")):
        return _abrir_csv(ruta)
    raise ErrorLista("El archivo tiene que ser Excel (.xlsx), CSV, TXT o PDF.")


def muestra(ruta, nombre=None, cantidad=5):
    """(columnas, primeras filas como dict) para mostrar en pantalla."""
    columnas, filas = abrir(ruta, nombre)
    primeras = []
    for fila in filas:
        primeras.append(dict(zip(columnas, fila)))
        if len(primeras) >= cantidad:
            break
    if not primeras:
        raise ErrorLista("No encontré filas con datos en el archivo.")
    return columnas, primeras


def _titulos(valores):
    """Nombres de las columnas de un encabezado, rellenando las que vienen vacías."""
    titulos, vistos = [], set()
    for i, v in enumerate(valores):
        titulo = str(v).strip() if str(v or "").strip() else f"Columna {i + 1}"
        while titulo in vistos:  # dos columnas con el mismo nombre
            titulo += " "
        vistos.add(titulo)
        titulos.append(titulo)
    return titulos


def _es_encabezado(fila):
    """La primera fila son títulos si tiene varias celdas de texto y ningún número.

    La lista de RSF arranca directamente con datos (y una fila rara de fecha), así
    que en ese caso las columnas se llaman "Columna 1", "Columna 2"…
    """
    llenas = [v for v in fila if str(v or "").strip()]
    return len(llenas) >= 2 and not any(_numero(v) is not None for v in llenas)


def _genericas(cantidad):
    return [f"Columna {i + 1}" for i in range(cantidad)]


def _encabezado_y_filas(primera, resto):
    """Decide los títulos mirando la primera fila y devuelve (columnas, generador)."""
    if _es_encabezado(primera):
        columnas = _titulos(primera)
        return columnas, resto
    columnas = _genericas(len(primera))

    def con_la_primera():
        yield primera
        yield from resto

    return columnas, con_la_primera()


def _sin_vacias(filas):
    for fila in filas:
        if any(str(v or "").strip() for v in fila):
            yield list(fila)


def _abrir_excel(ruta):
    import openpyxl

    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    hoja = libro[libro.sheetnames[0]]
    filas = _sin_vacias(hoja.iter_rows(max_row=MAX_FILAS, values_only=True))
    try:
        primera = next(filas)
    except StopIteration:
        raise ErrorLista("La primera hoja del Excel está vacía.")
    return _encabezado_y_filas(primera, filas)


def _abrir_csv(ruta):
    with open(ruta, "r", encoding="utf-8-sig", errors="replace") as f:
        muestra_texto = f.read(4000)
    try:
        dialecto = csv.Sniffer().sniff(muestra_texto, delimiters=";,\t|")
    except csv.Error:
        dialecto = csv.excel
        dialecto.delimiter = ";" if muestra_texto.count(";") > muestra_texto.count(",") else ","

    def leer():
        with open(ruta, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
            for i, fila in enumerate(csv.reader(f, dialecto)):
                if i >= MAX_FILAS:
                    break
                yield fila

    filas = _sin_vacias(leer())
    try:
        primera = next(filas)
    except StopIteration:
        raise ErrorLista("No encontré filas con datos en el archivo.")
    return _encabezado_y_filas(primera, filas)


# Una fila de una lista en PDF: código, descripción y los números del final.
NUMERO_SUELTO = re.compile(r"^-?[\d.,]*\d[\d.,]*$|^-$")


def _abrir_pdf(ruta):
    """Lee listas en PDF (las de FGC): código, descripción y los importes de la derecha."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ErrorLista("Falta la librería para leer PDF en el servidor.")
    try:
        lector = PdfReader(ruta)
        texto = "\n".join((p.extract_text() or "") for p in lector.pages)
    except Exception:
        raise ErrorLista("No pude abrir el PDF.")
    if not texto.strip():
        raise ErrorLista("El PDF no tiene texto: debe ser un escaneo. Pedile al proveedor el Excel, "
                         "o cargá esos precios a mano.")

    candidatas = []
    for linea in texto.splitlines():
        partes = linea.split()
        if len(partes) < 3:
            continue
        numeros = 0
        while numeros < len(partes) - 2 and NUMERO_SUELTO.match(partes[-1 - numeros]):
            numeros += 1
        if numeros >= 2:  # código + descripción + al menos dos importes
            corte = len(partes) - numeros
            candidatas.append([partes[0], " ".join(partes[1:corte])] + partes[corte:])
    if not candidatas:
        raise ErrorLista("No reconocí ninguna fila de precios en el PDF.")

    ancho = max(set(len(f) for f in candidatas), key=[len(f) for f in candidatas].count)
    filas = [f for f in candidatas if len(f) == ancho]
    return _genericas(ancho), iter(filas)


# ─────────────────────────── Comparación y aplicación ───────────────────────


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


def _indice(columnas, nombre):
    return columnas.index(nombre) if nombre in columnas else None


def _costo(fila, i_precio, i_envase, factor, equivalentes):
    """Costo de lista de una fila del archivo, o None si no se puede calcular."""
    precio = _numero(fila[i_precio]) if i_precio is not None and i_precio < len(fila) else None
    if not precio:
        return None
    if i_envase is not None and i_envase < len(fila):
        envase = _numero(fila[i_envase]) or 1
        envase = equivalentes.get(envase, envase)
        if envase:
            precio /= envase
    return round(precio * (factor or 1), 2)


def previsualizar(ruta, nombre, perfil):
    """Qué pasaría si se aplicara la lista: (cambios, sin_cambio, no_encontrados, sobrantes).

    - cambios: repuestos del proveedor cuyo costo cambia (con el costo y la venta nuevos)
    - sin_cambio: los que quedan igual
    - no_encontrados: repuestos del proveedor que no están en el archivo
    - sobrantes: filas del archivo que no corresponden a ningún repuesto nuestro
    """
    columnas, filas = abrir(ruta, nombre)
    i_codigo = _indice(columnas, perfil.get("col_codigo"))
    i_precio = _indice(columnas, perfil.get("col_precio"))
    if i_codigo is None or i_precio is None:
        raise ErrorLista("Elegí qué columna trae el código y cuál el precio.")
    i_marca = _indice(columnas, perfil.get("col_marca"))
    i_envase = _indice(columnas, perfil.get("col_envase"))
    factor = perfil.get("factor") or 1
    equivalentes = equivalencias(perfil.get("equivalencias"))
    campo = perfil.get("campo_codigo") or "nro_parte"

    repuestos = Repuesto.query.filter(Repuesto.proveedor == perfil["proveedor"],
                                      Repuesto.id != Repuesto.ID_VARIOS).order_by(Repuesto.nombre).all()
    # Los nuestros, indexados por código (y por código+marca cuando hay columna de marca)
    por_codigo, por_par = {}, {}
    for r in repuestos:
        codigo = _normalizar(getattr(r, campo, None))
        if not codigo:
            continue
        por_codigo.setdefault(codigo, []).append(r)
        if i_marca is not None:
            por_par.setdefault((codigo, _normalizar(r.marca_proveedor or r.marca)), []).append(r)

    costos, sobrantes = {}, 0
    for fila in filas:
        codigo = _normalizar(fila[i_codigo]) if i_codigo < len(fila) else ""
        if not codigo:
            continue
        nuestros = por_par.get((codigo, _normalizar(fila[i_marca] if i_marca < len(fila) else "")), []) \
            if i_marca is not None else []
        if not nuestros:
            mismos = por_codigo.get(codigo, [])
            # sin marca, o con marca que no coincide: solo sirve si no hay ambigüedad
            nuestros = mismos if (i_marca is None or len(mismos) == 1) else []
        if not nuestros:
            sobrantes += 1
            continue
        costo = _costo(fila, i_precio, i_envase, factor, equivalentes)
        if costo is None:
            continue
        for r in nuestros:
            costos.setdefault(r.id, costo)

    cambios, sin_cambio, no_encontrados = [], [], []
    for r in repuestos:
        costo = costos.get(r.id)
        if costo is None:
            no_encontrados.append(r)
            continue
        viejo = r.costo_lista or 0
        dato = {"repuesto": r, "costo_viejo": viejo, "costo_nuevo": costo,
                "variacion": (costo - viejo) / viejo * 100 if viejo else None,
                "venta_nueva": _venta_con(r, costo)}
        (sin_cambio if abs(costo - viejo) < 0.01 else cambios).append(dato)

    cambios.sort(key=lambda d: abs(d["variacion"] if d["variacion"] is not None else 999), reverse=True)
    return cambios, sin_cambio, no_encontrados, sobrantes


def _venta_con(repuesto, costo):
    """Precio de venta que quedaría, sin tocar el repuesto."""
    from .stock import markup_para

    costo_final = (costo or 0) * (1 - (repuesto.descuento_oferta or 0))
    return round(costo_final * markup_para(repuesto), 2)


def aplicar(cambios):
    """Guarda los costos nuevos y recalcula los precios de venta. No hace commit."""
    for dato in cambios:
        dato["repuesto"].costo_lista = dato["costo_nuevo"]
        recalcular_precio_venta(dato["repuesto"])
    db.session.flush()
    return len(cambios)
