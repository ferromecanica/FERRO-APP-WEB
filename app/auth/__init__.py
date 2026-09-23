import secrets

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Usuario

bp = Blueprint("auth", __name__)

EMAIL_TALLER = "taller@ferro.local"


def ingreso_automatico():
    """Con LOGIN_OBLIGATORIO apagado, todos entran como el usuario genérico 'Taller'."""
    if current_user.is_authenticated or request.endpoint in ("static", "sistema.backup") \
            or (request.endpoint or "").startswith("api."):
        return
    usuario = Usuario.query.filter_by(email=EMAIL_TALLER).first()
    if usuario is None:
        usuario = Usuario(email=EMAIL_TALLER, nombre="Taller Ferro", rol="Admin")
        usuario.set_password(secrets.token_hex(32))  # nadie la conoce: solo sirve para el ingreso automático
        db.session.add(usuario)
        try:
            db.session.commit()
        except IntegrityError:
            # Dos pedidos a la vez sobre una base sin el usuario: lo crean los dos
            # y el segundo choca con el email repetido. Me quedo con el que ganó.
            db.session.rollback()
            usuario = Usuario.query.filter_by(email=EMAIL_TALLER).one()
    login_user(usuario)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not current_app.config["LOGIN_OBLIGATORIO"]:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        usuario = Usuario.query.filter_by(email=email, activo=True).first()
        if usuario and usuario.check_password(request.form.get("password", "")):
            login_user(usuario, remember=bool(request.form.get("recordar")))
            siguiente = request.args.get("next")
            if not siguiente or not siguiente.startswith("/"):
                siguiente = url_for("dashboard.index")
            return redirect(siguiente)
        flash("Email o contraseña incorrectos.", "error")
    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
