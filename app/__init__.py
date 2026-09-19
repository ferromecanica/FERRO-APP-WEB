from flask import Flask

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
    from .dashboard import bp as dashboard_bp
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

    from .cli import register_cli
    from .filters import register_filters

    register_cli(app)
    register_filters(app)

    if not app.config["LOGIN_OBLIGATORIO"]:
        from .auth import ingreso_automatico

        app.before_request(ingreso_automatico)

    return app
