"""Punto de entrada WSGI (PythonAnywhere lo importa desde su archivo de configuración)."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
