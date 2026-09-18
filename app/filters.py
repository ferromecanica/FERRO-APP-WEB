from datetime import date, datetime


def pesos(valor, decimales=0):
    """$ 1.234.567 (formato argentino)."""
    if valor is None:
        return "—"
    txt = f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {txt}"


def numero(valor, decimales=0):
    if valor is None:
        return "—"
    return f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fecha(valor, fmt="%d/%m/%Y"):
    if not valor:
        return "—"
    if isinstance(valor, (date, datetime)):
        return valor.strftime(fmt)
    return str(valor)


def register_filters(app):
    app.jinja_env.filters["pesos"] = pesos
    app.jinja_env.filters["numero"] = numero
    app.jinja_env.filters["fecha"] = fecha

    @app.context_processor
    def inject_globals():
        return {"taller_nombre": app.config["TALLER_NOMBRE"], "hoy": date.today()}
