"""Reporte de mantenimiento en PDF.

Ferro arma el HTML (mismo diseño que el reporte de AppSheet) y lo manda al
Apps Script de docs/reportes_gdrive.gs, que agrega logo, firma y fotos desde
Drive, lo convierte a PDF, lo guarda en la carpeta de reportes y devuelve el link.
"""
import posixpath

from flask import render_template

from ..models import ConfigTaller
from . import drive

# Datos del membrete (los de AppSheet) si no están cargados en Configuración
TALLER_POR_DEFECTO = {
    "direccion": "Santa María de Oro 217 bis - CP (2000)",
    "localidad": "Rosario - Santa Fe",
    "telefono": "3416206823",
    "iva": "Responsable Inscripto",
}


class ErrorReporte(Exception):
    pass


def _si_no(valor):
    return "Sí" if valor else "No"


def armar_html(ot):
    """HTML del reporte (logo, firma y fotos quedan como marcas que completa el Apps Script)."""
    cfg = ConfigTaller.get()
    taller = dict(TALLER_POR_DEFECTO)
    if cfg.direccion:
        taller["direccion"] = cfg.direccion
    if cfg.telefono:
        taller["telefono"] = cfg.telefono

    fotos = [
        {"src": f"__FOTO:{posixpath.basename(foto.archivo)}__", "descripcion": foto.descripcion}
        for foto in ot.fotos if foto.en_reporte
    ]

    return render_template(
        "reportes/mantenimiento.html",
        ot=ot,
        taller=taller,
        logo="__LOGO__",
        firma="__FIRMA__",
        fluidos=[
            ("Aceite motor", _si_no(ot.aceite_motor), ot.aceite_motor_detalle),
            ("Aceite caja", _si_no(ot.aceite_caja), ot.aceite_caja_detalle),
            ("Aceite diferencial", _si_no(ot.aceite_diferencial), ot.aceite_diferencial_detalle),
        ],
        filtros1=[
            ("Filtro Aceite", _si_no(ot.filtro_aceite)),
            ("Filtro Aire", _si_no(ot.filtro_aire)),
            ("Filtro Habitáculo", _si_no(ot.filtro_habitaculo)),
        ],
        filtros2=[
            ("Filtro Combustible", _si_no(ot.filtro_combustible)),
            ("Scaneo", _si_no(ot.scaneo)),
            ("", ""),
        ],
        fotos=fotos,
    )


def nombre_archivo(ot):
    fecha = ot.fecha_fin or ot.fecha_ingreso
    return f"{fecha:%Y%m%d}_{ot.vehiculo.patente}_OT{ot.id}.pdf"


def configurado():
    return drive.configurado()


def generar_pdf(ot):
    """Genera el PDF en Drive y devuelve su link (lo guarda también en la OT)."""
    try:
        resultado = drive.llamar("reporte", nombre=nombre_archivo(ot), html=armar_html(ot))
    except drive.ErrorDrive as e:
        raise ErrorReporte(str(e).replace("Google Drive", "Google"))
    ot.link_reporte = resultado["url"]
    return ot.link_reporte
