"""Corre un comando en la consola Bash de PythonAnywhere y muestra la salida.

Uso:  .venv/bin/python scripts/servidor.py "comando"
"""
import sys
import time

from deploy import api


def ejecutar(comando, espera=60):
    consolas = [c for c in api("GET", "consoles/") if "bash" in c.get("executable", "")]
    if not consolas:
        sys.exit("No hay consola Bash abierta en PythonAnywhere: abrí una desde el navegador.")
    consola = consolas[0]["id"]
    marca = f"FIN-{int(time.time())}"
    api("POST", f"consoles/{consola}/send_input/", {"input": f"{comando}; echo {marca}\n"})
    salida = ""
    for _ in range(espera // 2):
        time.sleep(2)
        salida = api("GET", f"consoles/{consola}/get_latest_output/").get("output", "")
        if salida.rstrip().endswith(marca) or f"\n{marca}" in salida:
            break
    inicio = salida.rfind(comando[:30])
    return salida[inicio + len(comando[:30]):] if inicio >= 0 else salida[-1500:]


if __name__ == "__main__":
    print(ejecutar(sys.argv[1]))
