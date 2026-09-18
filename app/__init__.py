from flask import Flask

from config import Config

from .extensions import csrf, db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (registra los modelos)
    from .auth import bp as auth_bp
    from .clientes import bp as clientes_bp
    from .dashboard import bp as dashboard_bp
    from .ot import bp as ot_bp
    from .presupuestos import bp as presupuestos_bp
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

    from .cli import register_cli
    from .filters import register_filters

    register_cli(app)
    register_filters(app)

    if not app.config["LOGIN_OBLIGATORIO"]:
        from .auth import ingreso_automatico

        app.before_request(ingreso_automatico)

    with app.app_context():
        db.create_all()

    return app
