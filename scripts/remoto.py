"""Corre un comando en la consola Bash de PythonAnywhere y muestra la salida.

Uso:  python scripts/remoto.py "~/.venvs/ferro/bin/python scripts/vaciar.py --si"

Sirve para las tareas de una sola vez (importar, vaciar, crear un usuario).
Necesita una consola Bash abierta en el navegador, igual que el deploy.
El token sale de .deploy.env y nunca se muestra.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import USUARIO, api  # noqa: E402

ESPERA = 180  # segundos: importar el historial tarda un rato


def correr(comando, espera=ESPERA):
    consolas = [c for c in api("GET", "consoles/") if "bash" in c.get("executable", "")]
    if not consolas:
        nueva = api("POST", "consoles/", {"executable": "bash"})
        sys.exit("No hay consola Bash abierta. Creé una: abrila una vez en el navegador y volvé a probar:\n"
                 f"  https://www.pythonanywhere.com{nueva.get('console_url', '/consoles/')}")
    consola = consolas[0]["id"]

    marca = f"FIN-{int(time.time())}"
    api("POST", f"consoles/{consola}/send_input/",
        {"input": f"cd ~/FERRO && {comando}; echo {marca}-$?\n"})

    salida = ""
    for _ in range(espera // 2):
        time.sleep(2)
        salida = api("GET", f"consoles/{consola}/get_latest_output/").get("output", "")
        if marca in salida.replace(f"echo {marca}", ""):
            break
    desde = salida.find(comando[:40])
    print(salida[desde:] if desde > 0 else salida[-3000:])
    return f"{marca}-0" in salida


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(f"→ En {USUARIO}: {sys.argv[1]}")
    sys.exit(0 if correr(sys.argv[1]) else "✗ El comando no terminó bien (ver arriba).")
