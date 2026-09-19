"""API pública para el portal de clientes de ferromecanica.com.ar.

Reemplaza al doGet de Apps Script: misma entrada (email + patente) y mismo
formato de respuesta, así en la web solo cambia la dirección.
"""
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import csrf, db
from ..models import Cliente, OrdenTrabajo, Vehiculo
from ..validaciones import normalizar_patente

bp = Blueprint("api", __name__)
csrf.exempt(bp)

ORIGENES_PERMITIDOS = {"https://www.ferromecanica.com.ar", "https://ferromecanica.com.ar"}
MAX_FALLIDOS = 10          # intentos fallidos permitidos…
VENTANA_SEGUNDOS = 15 * 60  # …cada 15 minutos, por IP
_fallidos = defaultdict(deque)


def _ip():
    return request.headers.get("X-Real-IP") or request.remote_addr or "?"


def _bloqueada(ip):
    intentos = _fallidos[ip]
    while intentos and intentos[0] < time.time() - VENTANA_SEGUNDOS:
        intentos.popleft()
    return len(intentos) >= MAX_FALLIDOS


def _responder(datos, fallido=False):
    if fallido:
        _fallidos[_ip()].append(time.time())
    return jsonify(datos)


@bp.after_request
def _cors(respuesta):
    origen = request.headers.get("Origin")
    if origen in ORIGENES_PERMITIDOS:
        respuesta.headers["Access-Control-Allow-Origin"] = origen
        respuesta.headers["Vary"] = "Origin"
    return respuesta


@bp.route("/historial")
def historial():
    if _bloqueada(_ip()):
        return jsonify(error="Demasiados intentos. Probá de nuevo en unos minutos.")

    email = request.args.get("email", "").strip().lower()
    patente = normalizar_patente(request.args.get("patente"))
    if not email or not patente:
        return _responder({"error": "Faltan email o patente"}, fallido=True)

    clientes = Cliente.query.filter(func.lower(func.trim(Cliente.email)) == email).all()
    if not clientes:
        return _responder({"error": "Email no encontrado"}, fallido=True)
    vehiculo = Vehiculo.query.filter_by(patente=patente).first()

    # El cliente ve el auto si es su dueño actual o si le hicimos trabajos cuando era suyo
    for cliente in clientes:
        if vehiculo is None:
            break
        ordenes = (OrdenTrabajo.query.filter_by(cliente_id=cliente.id, vehiculo_id=vehiculo.id)
                   .order_by(OrdenTrabajo.id.desc()).all())
        if vehiculo.cliente_id == cliente.id or ordenes:
            return _responder({
                "cliente": cliente.nombre,
                "vehiculo": f"{vehiculo.marca or ''} {vehiculo.modelo or ''}".strip(),
                "historial": [{
                    "fecha": ot.fecha_fin.strftime("%d/%m/%Y") if ot.fecha_fin else "---",
                    "km": ot.km_entrada or "",
                    "detalle": ot.detalle or "",
                    "pdf": ot.link_reporte or "",
                    "proximo": ot.km_proximo_service or "",
                } for ot in ordenes],
            })
    return _responder({"error": "La patente no corresponde a este cliente"}, fallido=True)
