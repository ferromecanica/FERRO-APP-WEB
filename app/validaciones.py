"""Normalización y validación de datos que se cargan a mano (CUIT, patentes, teléfonos)."""
import re

MARCAS_COMUNES = [
    "Audi", "BMW", "Chery", "Chevrolet", "Citroën", "DS", "Fiat", "Ford", "Honda", "Hyundai",
    "Jeep", "Kia", "Mercedes-Benz", "Mitsubishi", "Nissan", "Peugeot", "RAM", "Renault",
    "Suzuki", "Toyota", "Volkswagen",
]

CONDICIONES_IVA = ["Consumidor Final", "Responsable Inscripto", "Monotributista", "Exento"]


def solo_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def normalizar_patente(texto):
    """'ab 123 cd' → 'AB123CD'. Limpia espacios y guiones; el formato lo revisa patente_valida."""
    return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())


# Los tres formatos que existen en Argentina
PATENTE_VIEJA = re.compile(r"^([A-Z]{3})(\d{3})$")          # AAA123, hasta 2016
PATENTE_MERCOSUR = re.compile(r"^[A-Z]{2}\d{3}[A-Z]{2}$")   # AB123CD
PATENTE_MOTO = re.compile(r"^[A-Z]\d{3}[A-Z]{3}$")          # A123BCD, motos Mercosur

# Para el auto que entra sin chapa (0 km, chapa perdida, sin papeles)
SIN_PATENTE = "SINPATENTE"

FORMATOS_PATENTE = ("AB123CD (Mercosur), A123BCD (moto) o AAA123 (la vieja). "
                    "Si el auto no tiene chapa, escribí SIN PATENTE")


def patente_valida(patente):
    """Solo los formatos reales: así no entra un «SINNUMERO» ni una patente a medias."""
    texto = patente or ""
    if texto == SIN_PATENTE:
        return True
    return bool(PATENTE_VIEJA.match(texto) or PATENTE_MERCOSUR.match(texto) or PATENTE_MOTO.match(texto))


def formato_patente(valor):
    """Qué chapón le corresponde y cómo se escribe el número."""
    texto = normalizar_patente(valor)
    if texto == SIN_PATENTE:
        return {"tipo": "otra", "texto": "SIN PATENTE"}
    vieja = PATENTE_VIEJA.match(texto)
    if vieja:
        return {"tipo": "vieja", "texto": f"{vieja.group(1)} {vieja.group(2)}"}
    if PATENTE_MERCOSUR.match(texto) or PATENTE_MOTO.match(texto):
        return {"tipo": "mercosur", "texto": texto}
    return {"tipo": "otra", "texto": texto}


def cuit_valido(cuit):
    """Verifica largo y dígito verificador (módulo 11)."""
    digitos = solo_digitos(cuit)
    if len(digitos) != 11:
        return False
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    resto = sum(int(d) * p for d, p in zip(digitos, pesos)) % 11
    verificador = 0 if resto == 0 else 9 if resto == 1 else 11 - resto
    return verificador == int(digitos[-1])


def formatear_cuit(cuit):
    d = solo_digitos(cuit)
    return f"{d[:2]}-{d[2:10]}-{d[10]}" if len(d) == 11 else cuit


def whatsapp_numero(telefono):
    """Arma el número internacional para wa.me a partir de lo que se haya cargado.

    '0341 15 328-6088', '341 3286088' o '+54 9 341 328 6088' → '5493413286088'.
    """
    d = solo_digitos(telefono)
    if not d:
        return None
    if d.startswith("549"):
        return d
    if d.startswith("54"):
        return "549" + d[2:]
    d = d.lstrip("0")
    # Sacar el 15 de celular que va después del código de área (2 a 4 dígitos)
    for largo_area in (2, 3, 4):
        if d[largo_area:largo_area + 2] == "15" and len(d) == 12:
            d = d[:largo_area] + d[largo_area + 2:]
            break
    return "549" + d if len(d) == 10 else None


def numero_ar(texto):
    """Interpreta números como se escriben acá: '12.500', '1.234,50', '0,5' o '0.5'.

    Devuelve float, o None si está vacío o no es un número.
    """
    t = (texto or "").strip().replace("$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") >= 1:
        partes = t.split(".")
        # '12.500' o '1.250.000' son miles; '0.5' o '2.75' son decimales
        if len(partes) > 2 or (len(partes[1]) == 3 and partes[0] not in ("", "0")):
            t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None
