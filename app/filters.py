from datetime import date, datetime

from .validaciones import whatsapp_numero


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


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def dia(valor, con_mes=False):
    """'martes 23/09', o 'hoy' y 'mañana' cuando corresponde (para la agenda de turnos)."""
    if not isinstance(valor, (date, datetime)):
        return fecha(valor)
    if isinstance(valor, datetime):
        valor = valor.date()
    faltan = (valor - date.today()).days
    if faltan == 0:
        etiqueta = "hoy"
    elif faltan == 1:
        etiqueta = "mañana"
    elif faltan == -1:
        etiqueta = "ayer"
    else:
        etiqueta = DIAS[valor.weekday()]
    if con_mes:
        return f"{etiqueta} {valor.day} de {MESES[valor.month - 1]}"
    return f"{etiqueta} {valor:%d/%m}"


def register_filters(app):
    app.jinja_env.filters["pesos"] = pesos
    app.jinja_env.filters["numero"] = numero
    app.jinja_env.filters["fecha"] = fecha
    app.jinja_env.filters["dia"] = dia
    app.jinja_env.filters["whatsapp"] = whatsapp_numero

    @app.context_processor
    def inject_globals():
        return {"taller_nombre": app.config["TALLER_NOMBRE"], "hoy": date.today()}
