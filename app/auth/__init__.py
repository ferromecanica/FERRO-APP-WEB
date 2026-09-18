from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from ..models import Usuario

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
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
