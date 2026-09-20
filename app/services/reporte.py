"""Reporte de mantenimiento en PDF.

Ferro arma el HTML (mismo diseño que el reporte de AppSheet) y lo manda al
Apps Script de docs/reportes_gdrive.gs, que agrega logo, firma y fotos desde
Drive, lo convierte a PDF, lo guarda en la carpeta de reportes y devuelve el link.
"""
import posixpath
from datetime import date

from flask import render_template

from ..models import ConfigTaller
from . import drive

# Datos del membrete (los de AppSheet) si no están cargados en Configuración
TALLER_POR_DEFECTO = {
    "direccion": "Santa María de Oro 217 bis - CP (2000)",
    "localidad": "Rosario - Santa Fe",
    "telefono": "3416206823",
    "iva": "Responsable Inscripto",
    "inicio": "01/02/2026",
}
DIAS_VALIDEZ_PRESUPUESTO = 15


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


def generar_pdf_presupuesto(presupuesto):
    """Genera el PDF del presupuesto en la carpeta de presupuestos de Drive y devuelve su link."""
    cfg = ConfigTaller.get()
    taller = dict(TALLER_POR_DEFECTO)
    if cfg.direccion:
        taller["direccion"] = cfg.direccion
    if cfg.telefono:
        taller["telefono"] = cfg.telefono
    html = render_template("reportes/presupuesto.html", p=presupuesto, taller=taller,
                           logo="__LOGO__", validez=DIAS_VALIDEZ_PRESUPUESTO)
    patente = presupuesto.vehiculo.patente if presupuesto.vehiculo else "SINPATENTE"
    nombre = f"{presupuesto.fecha:%Y%m%d}_{presupuesto.id}_{patente}.pdf"
    try:
        resultado = drive.llamar("reporte", nombre=nombre, html=html, carpeta="presupuestos")
    except drive.ErrorDrive as e:
        raise ErrorReporte(str(e).replace("Google Drive", "Google"))
    presupuesto.archivo_pdf = resultado["url"]
    return presupuesto.archivo_pdf


def nombre_archivo(ot):
    fecha = ot.fecha_fin or ot.fecha_ingreso
    return f"{fecha:%Y%m%d}_{ot.vehiculo.patente}_OT{ot.id}.pdf"


def generar_circular(cierre, datos):
    """Arma la circular contable del mes y la guarda en Drive. Devuelve el link."""
    cfg = ConfigTaller.get()
    taller = dict(TALLER_POR_DEFECTO)
    if cfg.direccion:
        taller["direccion"] = cfg.direccion
    if cfg.telefono:
        taller["telefono"] = cfg.telefono

    html = render_template("reportes/circular.html", c=cierre, taller=taller, logo="__LOGO__",
                           hoy=date.today(), **datos)
    nombre = f"{cierre.mes.replace('-', '')} circular{f' N{cierre.numero}' if cierre.numero else ''}.pdf"
    donde = {"carpeta_id": cfg.carpeta_circulares} if cfg.carpeta_circulares else {"carpeta": "circulares"}
    try:
        resultado = drive.llamar("reporte", nombre=nombre, html=html, **donde)
    except drive.ErrorDrive as e:
        raise ErrorReporte(str(e))
    cierre.link_circular = resultado["url"]
    return cierre.link_circular


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
