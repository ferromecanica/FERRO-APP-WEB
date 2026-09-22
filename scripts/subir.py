"""Sube un archivo a PythonAnywhere (los Excel de AppSheet, una lista de precios).

Uso:  python scripts/subir.py ~/Downloads/Taller_Mec.xlsx            (va a ~/FERRO/instance/)
      python scripts/subir.py ~/Downloads/lista.xlsx FERRO/instance/lista_rsf.xlsx

Va por la API de archivos, así que no hace falta tener la consola Bash abierta.
El token sale de .deploy.env, igual que el deploy.
"""
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import API, TOKEN, USUARIO  # noqa: E402

DESTINO_POR_DEFECTO = "FERRO/instance"


def subir(local, remoto):
    """Escribe el archivo en /home/<usuario>/<remoto>. Devuelve el destino."""
    datos = Path(local).read_bytes()
    borde = uuid.uuid4().hex
    cuerpo = (
        f"--{borde}\r\n"
        f'Content-Disposition: form-data; name="content"; filename="{Path(remoto).name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + datos + f"\r\n--{borde}--\r\n".encode()

    ruta = f"/home/{USUARIO}/{remoto.lstrip('/')}"
    req = urllib.request.Request(
        f"{API}/files/path{urllib.parse.quote(ruta)}", data=cuerpo, method="POST",
        headers={"Authorization": f"Token {TOKEN}",
                 "Content-Type": f"multipart/form-data; boundary={borde}"})
    try:
        urllib.request.urlopen(req, timeout=180)
    except urllib.error.HTTPError as e:
        sys.exit(f"Error {e.code} subiendo {Path(local).name}: {e.read().decode()[:300]}")
    return ruta, len(datos)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    local = Path(sys.argv[1]).expanduser()
    if not local.is_file():
        sys.exit(f"No encontré {local}")
    remoto = sys.argv[2] if len(sys.argv) > 2 else f"{DESTINO_POR_DEFECTO}/{local.name}"
    ruta, tamano = subir(local, remoto)
    print(f"✓ {local.name} → {ruta} ({tamano / 1024:.0f} KB)")
