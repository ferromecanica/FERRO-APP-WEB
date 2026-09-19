import getpass
from datetime import date, time, timedelta

import click

from .extensions import db
from .models import (
    Categoria,
    Cliente,
    ConfigTaller,
    OrdenTrabajo,
    RegistroHoras,
    Repuesto,
    Turno,
    Usuario,
    Vehiculo,
    Venta,
    VentaItem,
)


def register_cli(app):
    @app.cli.command("crear-usuario")
    @click.option("--email", prompt=True)
    @click.option("--nombre", prompt=True)
    @click.option("--rol", type=click.Choice(["Admin", "Mecanico"]), default="Admin", show_default=True)
    def crear_usuario(email, nombre, rol):
        """Crea un usuario (pide la contraseña sin mostrarla)."""
        if Usuario.query.filter_by(email=email).first():
            raise click.ClickException("Ya existe un usuario con ese email.")
        password = getpass.getpass("Contraseña: ")
        if len(password) < 8:
            raise click.ClickException("La contraseña debe tener al menos 8 caracteres.")
        u = Usuario(email=email, nombre=nombre, rol=rol)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Usuario {email} creado.")

    @app.cli.command("demo")
    def demo():
        """Carga unos pocos datos ficticios para ver la interfaz (solo en base vacía)."""
        if Cliente.query.first():
            raise click.ClickException("La base ya tiene datos; no cargo la demo.")
        cfg = ConfigTaller.get()
        cfg.valor_hora = 84000

        varios = Repuesto(id=Repuesto.ID_VARIOS, nombre="Varios / Mano de Obra", marca="N/A")
        filtros = Categoria(nombre="FILTROS")
        db.session.add_all([varios, filtros])
        db.session.add_all([
            Repuesto(id=1000, nombre="Kit filtros Mahle Corolla 1.8", proveedor="RSF", marca="MAHLE",
                     nro_parte="KIT47", categoria=filtros, stock_actual=3, stock_minimo=2,
                     precio_costo=10838, precio_venta=15173),
            Repuesto(id=1001, nombre="Helix HX7 10W-40 (litro)", proveedor="Shell", marca="SHELL",
                     stock_actual=1.5, stock_minimo=10, precio_costo=7067, precio_venta=8101),
        ])

        c1 = Cliente(nombre="Cliente Demo Uno", telefono="3410000001", condicion_iva="Consumidor Final")
        c2 = Cliente(nombre="Cliente Demo Dos", telefono="3410000002", condicion_iva="Responsable Inscripto")
        v1 = Vehiculo(patente="AA000AA", cliente=c1, marca="Peugeot", modelo="208", motor="1.6", anio=2019,
                      kilometraje=85000)
        v2 = Vehiculo(patente="AB111BB", cliente=c2, marca="Toyota", modelo="Corolla", motor="1.8", anio=2016,
                      kilometraje=140000)
        db.session.add_all([c1, c2, v1, v2])

        ot1 = OrdenTrabajo(id=10000, cliente=c1, vehiculo=v1, km_entrada=85000, detalle="Service 10.000 km",
                           estado="En proceso")
        ot2 = OrdenTrabajo(id=10001, cliente=c2, vehiculo=v2, km_entrada=140000, detalle="Frenos delanteros",
                           estado="Finalizada", fecha_fin=date.today(), total_cobrado=180000)
        db.session.add_all([ot1, ot2])
        db.session.add(RegistroHoras(ot=ot1, mecanico="Iván", horas=1.5, detalle="Cambio de aceite y filtros"))
        db.session.add(Turno(fecha=date.today() + timedelta(days=1), hora=time(9, 0), cliente=c2, vehiculo=v2,
                             motivo="Revisión tren delantero", estado="Confirmado"))
        venta = Venta(cliente=c2, ot=ot2, metodo_pago="Transferencia")
        venta.items.append(VentaItem(descripcion="Cambio de pastillas delanteras - OT 10001", cantidad=1,
                                     precio_unitario=180000, costo_unitario=65000))
        db.session.add(venta)
        db.session.commit()
        click.echo("Datos de demo cargados.")
