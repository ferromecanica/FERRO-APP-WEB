"""Publica la última versión en PythonAnywhere: git pull en el servidor + Reload.

Uso:  .venv/bin/python scripts/deploy.py

El token de la API se lee de .deploy.env (PA_API_TOKEN=...), que está en
.gitignore. El script nunca lo muestra.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USUARIO = "lucioroncoroni"
DOMINIO = f"{USUARIO}.pythonanywhere.com"
API = f"https://www.pythonanywhere.com/api/v0/user/{USUARIO}"
RAIZ = Path(__file__).resolve().parent.parent


def leer_token():
    archivo = RAIZ / ".deploy.env"
    if archivo.exists():
        for linea in archivo.read_text().splitlines():
            if linea.startswith("PA_API_TOKEN="):
                token = linea.split("=", 1)[1].strip()
                if token:
                    return token
    sys.exit("Falta el token: no encontré PA_API_TOKEN en .deploy.env")


TOKEN = leer_token()


def api(metodo, ruta, datos=None, timeout=30):
    cuerpo = urllib.parse.urlencode(datos).encode() if datos else None
    req = urllib.request.Request(f"{API}/{ruta}", data=cuerpo, method=metodo,
                                 headers={"Authorization": f"Token {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            texto = r.read().decode()
            return json.loads(texto) if texto else {}
    except urllib.error.HTTPError as e:
        detalle = e.read().decode()[:300]
        if e.code in (401, 403):
            sys.exit(f"PythonAnywhere rechazó el token ({e.code}). ¿Es el de la cuenta {USUARIO} y está vigente?")
        sys.exit(f"Error {e.code} en {ruta}: {detalle}")


def git(*args):
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True).stdout.strip()


def main():
    if git("status", "--porcelain"):
        sys.exit("Hay cambios sin commitear; commiteá antes de publicar.")
    subprocess.run(["git", "push", "-q"], cwd=RAIZ, check=True)
    version = git("rev-parse", "--short", "HEAD")
    print(f"→ Publicando {version}: {git('log', '-1', '--format=%s')}")

    consolas = [c for c in api("GET", "consoles/") if "bash" in c.get("executable", "")]
    if not consolas:
        nueva = api("POST", "consoles/", {"executable": "bash"})
        sys.exit("No había consola Bash abierta. Creé una: abrila una vez en el navegador y volvé a correr "
                 f"el deploy:\n  https://www.pythonanywhere.com{nueva.get('console_url', '/consoles/')}")
    consola = consolas[0]["id"]

    marca = f"DEPLOY-{version}-{int(time.time())}"
    comando = (
        "cd ~/FERRO && git pull --ff-only"
        " && ~/.venvs/ferro/bin/pip install -q -r requirements.txt"
        " && ~/.venvs/ferro/bin/python scripts/migrar.py"
        f" && echo {marca}-OK || echo {marca}-FALLO\n"
    )
    api("POST", f"consoles/{consola}/send_input/", {"input": comando})

    salida = ""
    for _ in range(90):
        time.sleep(2)
        salida = api("GET", f"consoles/{consola}/get_latest_output/").get("output", "")
        if f"{marca}-OK" in salida or f"{marca}-FALLO" in salida:
            break
    ultimo = salida[salida.rfind("git pull"):] if "git pull" in salida else salida[-800:]
    if f"{marca}-OK" not in salida:
        print(ultimo)
        sys.exit("✗ El git pull en el servidor no terminó bien (ver arriba).")
    print("✓ Código, librerías y base de datos actualizados en el servidor")

    try:
        api("POST", f"webapps/{DOMINIO}/reload/", timeout=120)
        print("✓ Web app recargada")
    except (TimeoutError, OSError):
        # A veces PythonAnywhere tarda en contestar aunque la recarga se hace igual: lo verifica el paso siguiente
        print("· La recarga tardó en responder; verifico el sitio…")
        time.sleep(10)

    try:
        with urllib.request.urlopen(f"https://{DOMINIO}/", timeout=60) as r:
            print(f"✓ https://{DOMINIO} responde ({r.status})")
    except urllib.error.HTTPError as e:
        sys.exit(f"✗ El sitio responde con error {e.code}: revisar el Error log en la pestaña Web.")


if __name__ == "__main__":
    main()
