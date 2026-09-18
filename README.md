# Ferro Taller

Sistema de gestión del taller mecánico Ferro. Reemplaza la app de AppSheet + Google Sheets.

**Stack:** Flask · SQLAlchemy · SQLite · HTMX. Pensado para correr en una cuenta **gratuita** de PythonAnywhere.

## Módulos

| Módulo | Estado |
|---|---|
| Login y usuarios (Admin / Mecánico) | ✅ |
| Tablero (OT abiertas, facturado y ganancia del mes, turnos, stock bajo) | ✅ |
| Clientes y vehículos (alta, edición, búsqueda en vivo, historial) | ✅ |
| Órdenes de trabajo | 🟡 listado y detalle (falta alta/edición, consumos, horas, fotos, reporte PDF) |
| Stock (repuestos, ingresos, movimientos) | 🟡 listados + lógica de consumo/reversión en `app/services/stock.py` |
| Presupuestos | 🟡 listado (falta armado y PDF) |
| Turnos | 🟡 listado |
| Ventas y resultado mensual | 🟡 listado + ganancia neta por mes |
| Migración desde Google Sheets | ⏳ pendiente |

## Correr en local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # y poner una SECRET_KEY propia
.venv/bin/flask --app wsgi crear-usuario
.venv/bin/flask --app wsgi demo  # opcional: datos ficticios para ver la interfaz
.venv/bin/flask --app wsgi run --debug
```

## Estructura

```
app/
  models.py          modelo de datos (equivalente a las hojas de Taller_Mec)
  services/stock.py  reglas de stock: consumir, revertir, ingresar, markups
  <módulo>/          un blueprint por sección (clientes, ot, stock, ventas…)
  templates/         Jinja, base.html tiene la barra lateral
  static/            ferro.css, logo.svg
config.py            configuración (lee .env)
wsgi.py              punto de entrada para PythonAnywhere
```

## Deploy en PythonAnywhere (cuenta gratuita)

> La cuenta gratuita permite **una sola web app**. Si `lroncoroni.pythonanywhere.com` ya tiene TGN Control,
> Ferro tiene que ir en otra cuenta gratuita (p. ej. `lucioroncoroni`).

1. Subir este repo a GitHub (GitHub está en la lista de sitios permitidos de la cuenta gratuita).
2. En una consola Bash de PythonAnywhere:
   ```bash
   git clone https://github.com/<usuario>/ferro.git ~/FERRO
   cd ~/FERRO
   python3.10 -m venv ~/.venvs/ferro
   ~/.venvs/ferro/bin/pip install -r requirements.txt
   cp .env.example .env && nano .env      # SECRET_KEY larga y aleatoria
   ~/.venvs/ferro/bin/flask --app wsgi crear-usuario
   ```
3. Pestaña **Web** → *Add a new web app* → *Manual configuration* → Python 3.10.
   - **Virtualenv:** `/home/<usuario>/.venvs/ferro`
   - **Static files:** URL `/static/` → `/home/<usuario>/FERRO/app/static`
   - **WSGI configuration file:** reemplazar todo por
     ```python
     import sys
     sys.path.insert(0, "/home/<usuario>/FERRO")
     from wsgi import app as application
     ```
   - Activar **Force HTTPS**.
4. *Reload*. Para actualizar después: `git pull` en la consola y *Reload*.

La base SQLite queda en `~/FERRO/instance/ferro.sqlite` (fuera de git). Conviene bajarla de vez en cuando como backup.
