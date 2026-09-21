import unicodedata

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate(render_as_batch=True)  # batch: SQLite no soporta ALTER COLUMN

login_manager.login_view = "auth.login"
login_manager.login_message = "Ingresá para continuar."
login_manager.login_message_category = "info"


def sin_acentos(texto):
    """'Distribución' → 'Distribucion'. Para buscar como uno escribe, sin acentos."""
    if texto is None:
        return None
    return "".join(c for c in unicodedata.normalize("NFD", str(texto))
                   if unicodedata.category(c) != "Mn")


@event.listens_for(Engine, "connect")
def _funciones_sqlite(conexion, _registro):
    """SQLite no sabe ignorar acentos: se la enseñamos para usarla en los buscadores."""
    if hasattr(conexion, "create_function"):
        conexion.create_function("sin_acentos", 1, sin_acentos)
