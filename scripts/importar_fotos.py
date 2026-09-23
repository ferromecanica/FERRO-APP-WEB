"""Trae las fotos de las OT que quedaron en el Drive de AppSheet.

Uso:  python scripts/importar_fotos.py <ruta al .xlsx> [--probar] [--carpeta Nombre=id ...]

En el Excel viene el nombre del archivo de cada foto ("Fotos_OT_Images/871f858f…jpg")
pero no la imagen. Este script le pide al Apps Script que copie cada una desde la
carpeta de AppSheet a la carpeta de fotos de Ferro, y guarda el id que devuelve.

Las de Fotos_OT van al reporte; las de Fotos_Taller son de uso interno.
Se puede cortar y volver a correr: sigue por donde iba (no copia dos veces).
Con --probar hace solo las primeras 5, para ver que funcione.
Con --carpeta se le dice qué carpeta de Drive es cuál, por si hay varias con el
mismo nombre. Hay tres Fotos_OT_Images en el Drive y la buena es la que está en
"SOFTWARE GESTIÓN (APPSHEET)", así que hay que pasarla siempre:
    --carpeta Fotos_OT_Images=1XbCu2_FdiR08_mzfzhPcsNifW2Cr1qjf
(Fotos_Taller_Images es única.) Para verlas: acción ver_carpetas del Apps Script.
"""
import posixpath
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import openpyxl  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import FotoOT, OrdenTrabajo  # noqa: E402
from app.services import drive  # noqa: E402

DE_A_VEZ = 25  # fotos por pedido: el Apps Script corta a los 6 minutos


def filas(libro, hoja):
    it = libro[hoja].iter_rows(values_only=True)
    encabezado = next(it)
    return [dict(zip(encabezado, r)) for r in it if r and r[0] is not None]


def numero_ot(valor):
    try:
        return int(float(str(valor)))
    except (TypeError, ValueError):
        return None


def momento(valor):
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.strptime(str(valor).strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def juntar(libro):
    """Todas las fotos del Excel: (carpeta de origen, archivo, ot, descripción, fecha, destino)."""
    pendientes = []
    for hoja, en_reporte in (("Fotos_OT", True), ("Fotos_Taller", False)):
        for f in filas(libro, hoja):
            ruta = str(f.get("Imagen") or "").strip()
            ot = numero_ot(f.get("ID_OT"))
            if not ruta or "/" not in ruta or ot is None:
                continue
            carpeta, archivo = ruta.split("/", 1)
            pendientes.append({
                "carpeta": carpeta, "archivo": posixpath.basename(archivo), "ot": ot,
                "descripcion": (str(f["Descripcion"]).strip()[:200] if f.get("Descripcion") else None),
                "fecha": momento(f.get("Fecha_Hora")), "en_reporte": en_reporte,
            })
    return pendientes


def importar(libro, probar=False, carpetas=None):
    todas = juntar(libro)
    existentes = {f.archivo for f in FotoOT.query.all()}
    ots = {o.id for o in OrdenTrabajo.query.all()}

    pendientes = [f for f in todas if f["archivo"] not in existentes and f["ot"] in ots]
    sin_ot = sum(1 for f in todas if f["ot"] not in ots)
    ya_estaban = len(todas) - len(pendientes) - sin_ot
    if probar:
        pendientes = pendientes[:5]
        print("(prueba: solo las primeras 5)")
    print(f"{len(todas)} fotos en el Excel · {ya_estaban} ya estaban · "
          f"{sin_ot} de OT que no tenemos · {len(pendientes)} para traer")

    # Los pedidos van por carpeta: el script de Google busca en una sola por vez
    por_carpeta = {}
    for f in pendientes:
        por_carpeta.setdefault(f["carpeta"], []).append(f)

    guardadas = perdidas = 0
    hechas = 0
    for carpeta, fotos in por_carpeta.items():
      for desde in range(0, len(fotos), DE_A_VEZ):
        tanda = fotos[desde:desde + DE_A_VEZ]
        elegida = (carpetas or {}).get(carpeta)
        donde = {"origen_id": elegida} if elegida else {"origen": carpeta}
        try:
            respuesta = drive.llamar("copiar_fotos", nombres="|".join(f["archivo"] for f in tanda), **donde)
        except drive.ErrorDrive as e:
            db.session.commit()
            sys.exit(f"✗ {e}\n  Guardadas hasta acá: {guardadas}. Volvé a correr el script para seguir.")
        ids = respuesta.get("fotos", {})
        for f in tanda:
            drive_id = ids.get(f["archivo"])
            if not drive_id:
                perdidas += 1
                continue
            db.session.add(FotoOT(
                ot_id=f["ot"], archivo=f["archivo"], drive_id=drive_id,
                en_reporte=f["en_reporte"], en_taller=not f["en_reporte"],
                descripcion=f["descripcion"], fecha_hora=f["fecha"] or datetime.now(),
            ))
            guardadas += 1
        db.session.commit()
        hechas += len(tanda)
        print(f"  {hechas:>4}/{len(pendientes)} · guardadas {guardadas}"
              + (f" · sin archivo en Drive {perdidas}" if perdidas else ""))
    return guardadas, perdidas


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    libro = openpyxl.load_workbook(sys.argv[1], data_only=True, read_only=True)
    app = create_app()
    with app.app_context():
        carpetas = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
        guardadas, perdidas = importar(libro, probar="--probar" in sys.argv, carpetas=carpetas)
        print(f"✓ {guardadas} fotos enganchadas a sus OT" + (f" · {perdidas} no estaban en Drive" if perdidas else ""))
        print(f"  Total en la base: {FotoOT.query.count()} fotos")
