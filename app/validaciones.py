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
    """'ab 123 cd' → 'AB123CD'. Acepta cualquier formato (motos, patentes viejas, extranjeras)."""
    return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())


def patente_valida(patente):
    return 5 <= len(patente) <= 8


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
