import os

from flask import Flask, request

from config import Config

from .extensions import csrf, db, login_manager, migrate


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (registra los modelos)
    from .api import bp as api_bp
    from .auth import bp as auth_bp
    from .clientes import bp as clientes_bp
    from .contable import bp as contable_bp
    from .cotizador import bp as cotizador_bp
    from .dashboard import bp as dashboard_bp
    from .movil import bp as movil_bp
    from .ot import bp as ot_bp
    from .presupuestos import bp as presupuestos_bp
    from .sistema import bp as sistema_bp
    from .stock import bp as stock_bp
    from .turnos import bp as turnos_bp
    from .ventas import bp as ventas_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(clientes_bp, url_prefix="/clientes")
    app.register_blueprint(turnos_bp, url_prefix="/turnos")
    app.register_blueprint(ot_bp, url_prefix="/ot")
    app.register_blueprint(presupuestos_bp, url_prefix="/presupuestos")
    app.register_blueprint(stock_bp, url_prefix="/stock")
    app.register_blueprint(ventas_bp, url_prefix="/ventas")
    app.register_blueprint(sistema_bp, url_prefix="/sistema")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(movil_bp, url_prefix="/movil")
    app.register_blueprint(cotizador_bp, url_prefix="/cotizador")
    app.register_blueprint(contable_bp, url_prefix="/administracion")

    @app.url_defaults
    def _version_de_archivos(endpoint, valores):
        """Agrega ?v=<fecha del archivo> a css/js: PythonAnywhere los cachea mucho tiempo."""
        if endpoint == "static" and "filename" in valores:
            try:
                valores["v"] = int(os.stat(os.path.join(app.static_folder, valores["filename"])).st_mtime)
            except OSError:
                pass

    from .cli import register_cli
    from .filters import register_filters

    register_cli(app)
    register_filters(app)

    if not app.config["LOGIN_OBLIGATORIO"]:
        from .auth import ingreso_automatico

        app.before_request(ingreso_automatico)

    from .services.backup import respaldar_si_toca

    @app.before_request
    def _backup_diario():
        """La primera visita del día manda la copia a Drive (acá no hay tareas programadas)."""
        if request.endpoint and request.endpoint != "static":
            respaldar_si_toca(app)

    return app
