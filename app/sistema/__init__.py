"""Endpoints de mantenimiento (no son pantallas para el usuario)."""
import gzip
import hmac
import os

from flask import Blueprint, Response, abort, current_app, request

from ..extensions import csrf
from ..services.backup import hacer_copia

bp = Blueprint("sistema", __name__)


@bp.route("/backup", methods=["POST"])
@csrf.exempt
def backup():
    """Hace una copia y la devuelve comprimida. La llama el Apps Script diario de Google Drive."""
    secreto = os.environ.get("BACKUP_SECRET", "")
    enviado = request.form.get("secreto", "")
    if not secreto or not hmac.compare_digest(secreto, enviado):
        abort(403)
    copia = hacer_copia(current_app.config["SQLALCHEMY_DATABASE_URI"])
    return Response(
        gzip.compress(copia.read_bytes()),
        mimetype="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{copia.name}.gz"'},
    )
