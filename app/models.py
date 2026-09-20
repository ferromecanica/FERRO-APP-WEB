"""Modelo de datos de Ferro.

Refleja las hojas del sistema AppSheet (Taller_Mec). Los totales que en
Sheets eran columnas calculadas (subtotales, horas insumidas, costo de mano
de obra) acá son propiedades, así nunca quedan desactualizados.

Los IDs de OT (10000…), presupuestos (40000…) y repuestos se conservan
como PK numérica para que la migración mantenga los números que ya conocen.
"""
from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class TimestampMixin:
    creado = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    actualizado = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ───────────────────────── Usuarios y configuración ─────────────────────────


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    rol = db.Column(db.String(20), default="Mecanico", nullable=False)  # Admin | Mecanico
    telefono = db.Column(db.String(30))
    password_hash = db.Column(db.String(256), nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password):
        # pbkdf2 funciona en cualquier build de Python (scrypt no siempre está disponible)
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def es_admin(self):
        return self.rol == "Admin"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))


class ConfigTaller(db.Model):
    """Una sola fila con los parámetros del taller (ex Datos_Taller)."""

    id = db.Column(db.Integer, primary_key=True)
    valor_hora = db.Column(db.Float, default=0, nullable=False)
    razon_social = db.Column(db.String(120))
    cuit = db.Column(db.String(20))
    direccion = db.Column(db.String(200))
    telefono = db.Column(db.String(30))

    @classmethod
    def get(cls):
        cfg = db.session.get(cls, 1)
        if cfg is None:
            cfg = cls(id=1, valor_hora=0)
            db.session.add(cfg)
            db.session.commit()
        return cfg


# ───────────────────────────── Clientes y vehículos ─────────────────────────


class Cliente(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, index=True)
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))
    direccion = db.Column(db.String(200))
    cuit = db.Column(db.String(20))
    condicion_iva = db.Column(db.String(40), default="Consumidor Final")
    notas = db.Column(db.Text)

    vehiculos = db.relationship("Vehiculo", back_populates="cliente", order_by="Vehiculo.patente")
    ordenes = db.relationship("OrdenTrabajo", back_populates="cliente", order_by="OrdenTrabajo.id.desc()")

    @property
    def codigo(self):
        return f"CLI-{self.id:03d}"

    @property
    def etiqueta(self):
        """Texto para elegirlo en un buscador: 'Nombre · CLI-003'."""
        return f"{self.nombre} · {self.codigo}"


class Vehiculo(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patente = db.Column(db.String(10), unique=True, nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"))  # puede no tener dueño asignado todavía
    marca = db.Column(db.String(40))
    modelo = db.Column(db.String(60))
    motor = db.Column(db.String(40))
    traccion = db.Column(db.String(20))
    color = db.Column(db.String(30))
    anio = db.Column(db.Integer)
    kilometraje = db.Column(db.Integer)
    vin = db.Column(db.String(30))
    ecu_marca = db.Column(db.String(40))
    ecu_modelo = db.Column(db.String(60))

    cliente = db.relationship("Cliente", back_populates="vehiculos")
    ordenes = db.relationship("OrdenTrabajo", back_populates="vehiculo", order_by="OrdenTrabajo.id.desc()")

    @property
    def descripcion(self):
        return " ".join(p for p in [self.marca, self.modelo, self.motor] if p)


# ─────────────────────────────────── Turnos ─────────────────────────────────


ESTADOS_TURNO = ["Pendiente", "Confirmado", "Ingresado", "Cancelado"]


class Turno(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    hora = db.Column(db.Time)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"))
    vehiculo_id = db.Column(db.Integer, db.ForeignKey("vehiculo.id"))
    contacto = db.Column(db.String(120))  # para turnos de gente que todavía no es cliente
    telefono = db.Column(db.String(30))
    motivo = db.Column(db.String(200))
    estado = db.Column(db.String(20), default="Pendiente")  # Pendiente | Confirmado | Cancelado | Ingresado
    observaciones = db.Column(db.Text)
    duracion_valor = db.Column(db.Float)
    duracion_unidad = db.Column(db.String(10))  # Horas | Días

    cliente = db.relationship("Cliente")
    vehiculo = db.relationship("Vehiculo")
    ot = db.relationship("OrdenTrabajo", back_populates="turno", uselist=False)  # la OT que salió del turno

    @property
    def quien(self):
        """Nombre a mostrar: el cliente si está cargado, si no el contacto suelto."""
        return self.cliente.nombre if self.cliente else (self.contacto or "Sin nombre")

    @property
    def telefono_util(self):
        return self.telefono or (self.cliente.telefono if self.cliente else None)

    @property
    def duracion(self):
        if not self.duracion_valor:
            return None
        valor = int(self.duracion_valor) if self.duracion_valor == int(self.duracion_valor) else self.duracion_valor
        unidad = (self.duracion_unidad or "Horas").lower()
        return f"{valor} {unidad[:-1] if valor == 1 else unidad}"


# ───────────────────────────── Órdenes de trabajo ───────────────────────────

ESTADOS_OT = ["Pendiente", "En proceso", "Finalizada"]
ESTADOS_OT_ABIERTA = ESTADOS_OT[:2]
CLASIFICACIONES_CIERRE = ["Servicio", "Otro"]  # "Servicio" = mantenimiento con reporte
MOTIVOS_SIN_CARGO = ["Auto propio", "Cortesía", "Garantía", "Otro"]


class OrdenTrabajo(TimestampMixin, db.Model):
    __tablename__ = "orden_trabajo"

    id = db.Column(db.Integer, primary_key=True)  # número de OT (10000…)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"))  # se puede completar al cerrar
    vehiculo_id = db.Column(db.Integer, db.ForeignKey("vehiculo.id"), nullable=False)
    turno_id = db.Column(db.Integer, db.ForeignKey("turno.id"))
    fecha_ingreso = db.Column(db.Date, default=date.today, nullable=False)
    km_entrada = db.Column(db.Integer)
    detalle = db.Column(db.Text)
    estado = db.Column(db.String(30), default="Pendiente", nullable=False)
    presupuesto_cliente = db.Column(db.Float)
    total_cobrado = db.Column(db.Float)
    fecha_fin = db.Column(db.Date)
    clasificacion_cierre = db.Column(db.String(40))
    sin_cargo = db.Column(db.Boolean, default=False, nullable=False)  # auto propio, cortesía, garantía
    motivo_sin_cargo = db.Column(db.String(120))
    km_proximo_service = db.Column(db.Integer)
    link_reporte = db.Column(db.String(300))

    # Checklist de service para el reporte de mantenimiento
    aceite_motor = db.Column(db.Boolean, default=False)
    aceite_motor_detalle = db.Column(db.String(120))
    aceite_caja = db.Column(db.Boolean, default=False)
    aceite_caja_detalle = db.Column(db.String(120))
    aceite_diferencial = db.Column(db.Boolean, default=False)
    aceite_diferencial_detalle = db.Column(db.String(120))
    filtro_aceite = db.Column(db.Boolean, default=False)
    filtro_aire = db.Column(db.Boolean, default=False)
    filtro_habitaculo = db.Column(db.Boolean, default=False)
    filtro_combustible = db.Column(db.Boolean, default=False)
    scaneo = db.Column(db.Boolean, default=False)
    otros = db.Column(db.Text)

    cliente = db.relationship("Cliente", back_populates="ordenes")
    vehiculo = db.relationship("Vehiculo", back_populates="ordenes")
    turno = db.relationship("Turno", back_populates="ot")
    tareas = db.relationship("TareaOT", back_populates="ot", cascade="all, delete-orphan")
    horas = db.relationship("RegistroHoras", back_populates="ot", cascade="all, delete-orphan")
    consumos = db.relationship("ConsumoOT", back_populates="ot", cascade="all, delete-orphan")
    fotos = db.relationship("FotoOT", back_populates="ot", cascade="all, delete-orphan")
    ventas = db.relationship("Venta", back_populates="ot")

    @property
    def horas_insumidas(self):
        return sum(h.horas or 0 for h in self.horas)

    @property
    def total_repuestos(self):
        return sum(c.subtotal for c in self.consumos)

    @property
    def costo_repuestos(self):
        return sum(c.subtotal_costo for c in self.consumos)

    @property
    def abierta(self):
        return self.estado in ESTADOS_OT_ABIERTA

    @property
    def venta(self):
        return self.ventas[0] if self.ventas else None

    @property
    def por_cobrar(self):
        """Trabajo terminado pero todavía sin cobrar (sin venta registrada).

        Las que se cerraron sin cargo no cuentan: no hay nada que cobrar.
        """
        return self.estado == "Finalizada" and not self.ventas and not self.sin_cargo

    @classmethod
    def proximo_numero(cls):
        ultimo = db.session.query(db.func.max(cls.id)).scalar()
        return (ultimo or 9999) + 1


class TareaOT(db.Model):
    """Tareas extra detectadas/realizadas en la OT (ex Tareas_extra_OT)."""

    id = db.Column(db.Integer, primary_key=True)
    ot_id = db.Column(db.Integer, db.ForeignKey("orden_trabajo.id"), nullable=False)
    descripcion = db.Column(db.String(300), nullable=False)

    ot = db.relationship("OrdenTrabajo", back_populates="tareas")


class RegistroHoras(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ot_id = db.Column(db.Integer, db.ForeignKey("orden_trabajo.id"), nullable=False)
    fecha = db.Column(db.Date, default=date.today, nullable=False)
    mecanico = db.Column(db.String(60), nullable=False)
    horas = db.Column(db.Float, nullable=False)
    detalle = db.Column(db.String(300))

    ot = db.relationship("OrdenTrabajo", back_populates="horas")


class ConsumoOT(db.Model):
    """Repuesto/insumo usado en una OT. Al crearlo descuenta stock (ver services.stock)."""

    id = db.Column(db.Integer, primary_key=True)
    ot_id = db.Column(db.Integer, db.ForeignKey("orden_trabajo.id"), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey("repuesto.id"), nullable=False)
    descripcion = db.Column(db.String(300))  # nombre registrado o detalle de "Varios"
    cantidad = db.Column(db.Float, nullable=False)
    precio_unitario = db.Column(db.Float, default=0, nullable=False)
    precio_costo = db.Column(db.Float, default=0, nullable=False)  # congelado al momento del consumo
    fecha = db.Column(db.Date, default=date.today, nullable=False)

    ot = db.relationship("OrdenTrabajo", back_populates="consumos")
    repuesto = db.relationship("Repuesto", back_populates="consumos")

    @property
    def subtotal(self):
        return (self.cantidad or 0) * (self.precio_unitario or 0)

    @property
    def subtotal_costo(self):
        return (self.cantidad or 0) * (self.precio_costo or 0)


class FotoOT(db.Model):
    """Foto de una OT, guardada en la carpeta de fotos de Drive.

    Cada foto puede ir al reporte (registro fotográfico del PDF), al taller
    (uso interno) o a ambos.
    """

    id = db.Column(db.Integer, primary_key=True)
    ot_id = db.Column(db.Integer, db.ForeignKey("orden_trabajo.id"), nullable=False)
    archivo = db.Column(db.String(300), nullable=False)  # nombre del archivo en la carpeta de fotos de Drive
    drive_id = db.Column(db.String(100))  # id del archivo en Drive (para mostrarla)
    en_reporte = db.Column(db.Boolean, default=True, nullable=False)
    en_taller = db.Column(db.Boolean, default=False, nullable=False)
    descripcion = db.Column(db.String(200))
    fecha_hora = db.Column(db.DateTime, default=datetime.now)

    ot = db.relationship("OrdenTrabajo", back_populates="fotos")

    @property
    def destino(self):
        if self.en_reporte and self.en_taller:
            return "ambos"
        return "reporte" if self.en_reporte else "taller"

    @property
    def miniatura(self):
        return f"https://drive.google.com/thumbnail?id={self.drive_id}&sz=w600" if self.drive_id else None

    @property
    def grande(self):
        return f"https://drive.google.com/thumbnail?id={self.drive_id}&sz=w1600" if self.drive_id else None

    @property
    def url(self):
        return f"https://drive.google.com/file/d/{self.drive_id}/view" if self.drive_id else None


# ─────────────────────────────────── Stock ──────────────────────────────────


class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(60), unique=True, nullable=False)

    subcategorias = db.relationship("Subcategoria", back_populates="categoria", order_by="Subcategoria.nombre")


class Subcategoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(60), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categoria.id"), nullable=False)

    categoria = db.relationship("Categoria", back_populates="subcategorias")


class Proveedor(db.Model):
    """Proveedores de repuestos (el nombre es lo que usan repuestos, markups e ingresos)."""

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)


class FotoRepuesto(db.Model):
    """Foto de un repuesto, guardada en Drive (subcarpeta Repuestos de la carpeta de fotos)."""

    id = db.Column(db.Integer, primary_key=True)
    repuesto_id = db.Column(db.Integer, db.ForeignKey("repuesto.id"), nullable=False)
    archivo = db.Column(db.String(300), nullable=False)
    drive_id = db.Column(db.String(100))
    descripcion = db.Column(db.String(200))
    fecha_hora = db.Column(db.DateTime, default=datetime.now)

    repuesto = db.relationship("Repuesto", back_populates="fotos")

    @property
    def miniatura(self):
        return f"https://drive.google.com/thumbnail?id={self.drive_id}&sz=w600" if self.drive_id else None

    @property
    def grande(self):
        return f"https://drive.google.com/thumbnail?id={self.drive_id}&sz=w1600" if self.drive_id else None

    @property
    def url(self):
        return f"https://drive.google.com/file/d/{self.drive_id}/view" if self.drive_id else None


class ConfigMarkup(db.Model):
    """Markup por proveedor + marca/envase (ex Config_Markups)."""

    id = db.Column(db.Integer, primary_key=True)
    proveedor = db.Column(db.String(60), nullable=False)
    marca_envase = db.Column(db.String(60))
    markup = db.Column(db.Float, nullable=False)


class PerfilLista(db.Model):
    """Cómo leer la lista de precios de un proveedor (qué columna es cuál).

    Se guarda cuando se actualizan precios, así la próxima vez ya viene elegido.
    """

    id = db.Column(db.Integer, primary_key=True)
    proveedor = db.Column(db.String(60), nullable=False, unique=True)
    col_codigo = db.Column(db.String(120))
    col_marca = db.Column(db.String(120))
    col_precio = db.Column(db.String(120), nullable=False)
    col_envase = db.Column(db.String(120))
    campo_codigo = db.Column(db.String(20), default="nro_parte")  # nro_parte | cod_proveedor | codigo_barras
    factor = db.Column(db.Float, default=1.0)  # lo que hay que multiplicar para llegar al costo
    equivalencias = db.Column(db.String(120))  # envases que se cuentan distinto, ej. "16=4"
    actualizada = db.Column(db.DateTime)
    # Forma del último archivo que se aplicó bien, para avisar si el próximo viene distinto
    columnas = db.Column(db.Text)  # nombres de las columnas separados por |
    filas = db.Column(db.Integer)

    @property
    def nombres_columnas(self):
        return [c for c in (self.columnas or "").split("|") if c]


class Repuesto(TimestampMixin, db.Model):
    ID_VARIOS = 99  # "Varios / Mano de Obra": ítem genérico sin control de stock

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, index=True)
    proveedor = db.Column(db.String(60))
    marca = db.Column(db.String(60))
    nro_parte = db.Column(db.String(60), index=True)
    codigo_barras = db.Column(db.String(60), index=True)
    cod_proveedor = db.Column(db.String(60))
    marca_proveedor = db.Column(db.String(60))  # ex Marca_RSF, clave para el markup
    categoria_id = db.Column(db.Integer, db.ForeignKey("categoria.id"))
    subcategoria_id = db.Column(db.Integer, db.ForeignKey("subcategoria.id"))
    stock_actual = db.Column(db.Float, default=0, nullable=False)
    stock_minimo = db.Column(db.Float, default=0)
    # Costo: costo_lista (de la lista del proveedor o cargado a mano) menos el descuento de oferta
    # = precio_costo (costo final, el que se usa para la ganancia). Venta = costo final × markup.
    costo_lista = db.Column(db.Float, default=0, nullable=False)
    descuento_oferta = db.Column(db.Float)  # fracción: 0.05 = 5 %
    precio_costo = db.Column(db.Float, default=0, nullable=False)
    costo_manual = db.Column(db.Boolean, default=False)  # True: la actualización de listas no pisa el costo
    markup = db.Column(db.Float)  # si es None se toma de ConfigMarkup
    precio_venta = db.Column(db.Float, default=0, nullable=False)
    comp_marca = db.Column(db.String(60))
    comp_modelo = db.Column(db.String(120))
    comp_motor = db.Column(db.String(60))
    detalle = db.Column(db.Text)
    estanteria = db.Column(db.String(30))  # ubicación en el taller (opcional)
    estante = db.Column(db.String(30))
    foto = db.Column(db.String(300))

    categoria = db.relationship("Categoria")
    subcategoria = db.relationship("Subcategoria")
    movimientos = db.relationship("MovimientoStock", back_populates="repuesto", order_by="MovimientoStock.fecha.desc()")
    consumos = db.relationship("ConsumoOT", back_populates="repuesto")      # dónde se usó, en OTs
    ventas = db.relationship("VentaItem", back_populates="repuesto")        # y en ventas de mostrador
    fotos = db.relationship("FotoRepuesto", back_populates="repuesto", order_by="FotoRepuesto.id",
                            cascade="all, delete-orphan")

    @property
    def usos(self):
        """Dónde se usó el repuesto: consumos de OT y renglones de ventas, del más nuevo al más viejo."""
        salidas = [
            {"fecha": c.fecha, "ot": c.ot, "venta": None, "cantidad": c.cantidad,
             "precio": c.precio_unitario, "costo": c.precio_costo, "descripcion": c.descripcion}
            for c in self.consumos
        ]
        salidas += [
            {"fecha": i.venta.fecha, "ot": i.venta.ot, "venta": i.venta, "cantidad": i.cantidad,
             "precio": i.precio_unitario, "costo": i.costo_unitario, "descripcion": i.descripcion}
            for i in self.ventas if i.venta is not None and i.venta.ot_id is None
        ]
        return sorted(salidas, key=lambda s: s["fecha"] or date.min, reverse=True)

    @property
    def ubicacion(self):
        partes = [p for p in (self.estanteria, self.estante) if p]
        return " · ".join(partes)

    @property
    def controla_stock(self):
        return self.id != self.ID_VARIOS

    @property
    def bajo_stock(self):
        return self.controla_stock and self.stock_actual <= (self.stock_minimo or 0)


# ────────────────────────────── Administración ──────────────────────────────

TIPOS_MOVIMIENTO_CONTABLE = ["Ingreso", "Egreso", "Colchón"]
# Las mismas de la app contable, en el mismo orden. Se puede escribir otra.
CLASIFICACIONES = ["Gasto Corriente", "Inversión de Capital", "Ventas", "Repuestos y Proveedores",
                   "Gasto Operativo", "Gasto menor", "Bien de uso", "Sueldos"]
COMPROBANTES = ["S/C", "Factura A", "Factura B", "Factura C", "Ticket", "Liquidación", "Recibo"]
TIPOS_CAPITAL = ["Aporte de Capital", "Devolución de Capital"]


class Socio(db.Model):
    """Los dueños del taller: sueldo de referencia y cuánto le toca a cada uno."""

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(60), unique=True, nullable=False)
    rol = db.Column(db.String(60))
    sueldo_base = db.Column(db.Float, default=0)
    participacion = db.Column(db.Float, default=0.5)  # 0,5 = mitad y mitad
    alias = db.Column(db.String(60))
    orden = db.Column(db.Integer, default=0)  # en el reparto de sueldos, el primero cobra primero

    aportes = db.relationship("AporteCapital", back_populates="socio")

    @property
    def capital_pesos(self):
        return sum(a.pesos_con_signo for a in self.aportes)

    @property
    def capital_usd(self):
        return sum(a.usd_con_signo for a in self.aportes)


class MovimientoContable(db.Model):
    """Lo que entra y sale de la caja del taller (ex Movimientos de la app contable).

    Los que salen de una venta o de una compra de repuestos se generan solos y
    quedan atados a su origen, para no cargar dos veces lo mismo.
    """

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)  # Ingreso | Egreso | Colchón
    mes_imputacion = db.Column(db.String(7), nullable=False, index=True)  # "2026-08"
    clasificacion = db.Column(db.String(40))
    comprobante = db.Column(db.String(20), default="S/C")
    nro_comprobante = db.Column(db.String(40))
    quien = db.Column(db.String(120))  # proveedor o cliente
    cuit = db.Column(db.String(15))
    concepto = db.Column(db.String(300))
    neto = db.Column(db.Float, default=0)
    iva = db.Column(db.Float, default=0)
    percepciones = db.Column(db.Float, default=0)
    no_gravado = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0, nullable=False)
    cobrado = db.Column(db.Boolean, default=True, nullable=False)  # los ingresos suman al cierre si están cobrados
    venta_id = db.Column(db.Integer, db.ForeignKey("venta.id"))
    ingreso_id = db.Column(db.Integer, db.ForeignKey("ingreso_stock.id"))
    cierre_id = db.Column(db.Integer, db.ForeignKey("cierre_mensual.id"))  # lo generó un cierre
    origen = db.Column(db.String(40), index=True)  # id que tenía en la app contable de AppSheet

    venta = db.relationship("Venta")
    ingreso = db.relationship("IngresoStock")
    cierre = db.relationship("CierreMensual", back_populates="movimientos")

    @property
    def automatico(self):
        """Lo generó Ferro (una venta, una compra o un cierre): no se edita a mano."""
        return bool(self.venta_id or self.ingreso_id or self.cierre_id)

    @property
    def signo(self):
        return -1 if self.tipo == "Egreso" else 1

    @staticmethod
    def mes_de(fecha):
        return f"{fecha:%Y-%m}"


class AporteCapital(db.Model):
    """Plata que un socio pone (o saca) del taller, en pesos y en dólares del día."""

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    socio_id = db.Column(db.Integer, db.ForeignKey("socio.id"), nullable=False)
    tipo = db.Column(db.String(30), default="Aporte de Capital", nullable=False)
    pesos = db.Column(db.Float, default=0, nullable=False)
    cotizacion = db.Column(db.Float)  # cuánto valía el dólar ese día
    notas = db.Column(db.String(300))
    cierre_id = db.Column(db.Integer, db.ForeignKey("cierre_mensual.id"))  # devolución hecha en un cierre
    origen = db.Column(db.String(40), index=True)  # id que tenía en la app contable de AppSheet

    socio = db.relationship("Socio", back_populates="aportes")
    cierre = db.relationship("CierreMensual", back_populates="devoluciones")

    @property
    def usd(self):
        return round(self.pesos / self.cotizacion, 2) if self.cotizacion else 0

    @property
    def devuelve(self):
        return self.tipo == "Devolución de Capital"

    @property
    def pesos_con_signo(self):
        return -self.pesos if self.devuelve else self.pesos

    @property
    def usd_con_signo(self):
        return -self.usd if self.devuelve else self.usd


class CierreMensual(db.Model):
    """El cierre de un mes: qué entró, qué salió y cómo se reparte.

    Al cerrar se guardan los números tal como quedaron (después los movimientos
    pueden cambiar, pero el cierre es el cierre) y se generan las liquidaciones
    de sueldo, la devolución de capital y el colchón del mes siguiente.
    """

    id = db.Column(db.Integer, primary_key=True)
    mes = db.Column(db.String(7), unique=True, nullable=False)  # "2026-08"
    fecha_cierre = db.Column(db.Date)
    cotizacion = db.Column(db.Float)
    estado = db.Column(db.String(20), default="Abierto")  # Abierto | Cerrado
    modo = db.Column(db.String(12), default="Automático")  # Automático | Manual
    notas = db.Column(db.Text)

    # Cómo quedó (se completa al cerrar)
    ingresos = db.Column(db.Float, default=0)
    egresos = db.Column(db.Float, default=0)
    colchon_entrante = db.Column(db.Float, default=0)
    repago = db.Column(db.Float, default=0)
    ganancia = db.Column(db.Float, default=0)
    colchon = db.Column(db.Float, default=0)  # lo que se guarda para el mes que viene

    socios = db.relationship("CierreSocio", back_populates="cierre", cascade="all, delete-orphan")
    movimientos = db.relationship("MovimientoContable", back_populates="cierre")
    devoluciones = db.relationship("AporteCapital", back_populates="cierre")

    @property
    def resultado(self):
        return (self.ingresos or 0) - (self.egresos or 0) + (self.colchon_entrante or 0)

    @property
    def sueldos(self):
        return sum(s.sueldo or 0 for s in self.socios)

    @property
    def cerrado(self):
        return self.estado == "Cerrado"


class CierreSocio(db.Model):
    """Lo que le tocó a cada socio en un cierre."""

    id = db.Column(db.Integer, primary_key=True)
    cierre_id = db.Column(db.Integer, db.ForeignKey("cierre_mensual.id"), nullable=False)
    socio_id = db.Column(db.Integer, db.ForeignKey("socio.id"), nullable=False)
    sueldo = db.Column(db.Float, default=0)
    repago = db.Column(db.Float, default=0)
    ganancia = db.Column(db.Float, default=0)

    cierre = db.relationship("CierreMensual", back_populates="socios")
    socio = db.relationship("Socio")

    @property
    def total(self):
        return (self.sueldo or 0) + (self.repago or 0) + (self.ganancia or 0)


class MovimientoStock(db.Model):
    """Libro de stock. Cantidad con signo: + entra, − sale. Nunca se borra, se revierte."""

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)
    repuesto_id = db.Column(db.Integer, db.ForeignKey("repuesto.id"), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # Ingreso | Consumo | Venta | Reversion | Ajuste
    ot_id = db.Column(db.Integer, db.ForeignKey("orden_trabajo.id"))
    venta_id = db.Column(db.Integer, db.ForeignKey("venta.id"))
    ingreso_id = db.Column(db.Integer, db.ForeignKey("ingreso_stock.id"))
    detalle = db.Column(db.String(300))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"))
    stock_resultante = db.Column(db.Float)  # cómo quedó el stock después del movimiento

    repuesto = db.relationship("Repuesto", back_populates="movimientos")
    usuario = db.relationship("Usuario")

    @property
    def stock_anterior(self):
        if self.stock_resultante is None:
            return None
        return self.stock_resultante - (self.cantidad or 0)


class IngresoStock(TimestampMixin, db.Model):
    """Compra a proveedor (ex Ingresos_Cabecera). Al confirmar suma stock."""

    __tablename__ = "ingreso_stock"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, default=date.today, nullable=False)
    proveedor = db.Column(db.String(120), nullable=False)
    nro_factura = db.Column(db.String(40))
    notas = db.Column(db.Text)
    estado = db.Column(db.String(20), default="Borrador")  # Borrador | Confirmado | Anulado

    items = db.relationship("IngresoStockItem", back_populates="ingreso", cascade="all, delete-orphan",
                            order_by="IngresoStockItem.id")

    @property
    def total(self):
        return sum(i.subtotal for i in self.items)

    @property
    def editable(self):
        return self.estado == "Borrador"


class IngresoStockItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingreso_id = db.Column(db.Integer, db.ForeignKey("ingreso_stock.id"), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey("repuesto.id"), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    costo_unitario = db.Column(db.Float)

    ingreso = db.relationship("IngresoStock", back_populates="items")
    repuesto = db.relationship("Repuesto")

    @property
    def subtotal(self):
        return (self.cantidad or 0) * (self.costo_unitario or 0)


# ──────────────────────────────── Presupuestos ──────────────────────────────


ESTADOS_PRESUPUESTO = ["Borrador", "Enviado", "Aprobado", "Rechazado"]


class Presupuesto(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)  # número (40000…)
    fecha = db.Column(db.Date, default=date.today, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"), nullable=False)
    vehiculo_id = db.Column(db.Integer, db.ForeignKey("vehiculo.id"))
    estado = db.Column(db.String(20), default="Borrador")  # Borrador | Enviado | Aprobado | Rechazado | Finalizado
    modo_mano_obra = db.Column(db.String(20), default="Por horas")  # Por horas | Por monto
    horas_mano_obra = db.Column(db.Float)
    valor_hora = db.Column(db.Float)  # congelado al crear el presupuesto
    monto_fijo_mo = db.Column(db.Float)
    mostrar_precios_detalle = db.Column(db.Boolean, default=True)
    archivado = db.Column(db.Boolean, default=False, nullable=False)  # fuera del listado, sin borrarlo
    archivo_pdf = db.Column(db.String(300))

    cliente = db.relationship("Cliente")
    vehiculo = db.relationship("Vehiculo")
    trabajos = db.relationship("PresupuestoTrabajo", back_populates="presupuesto", cascade="all, delete-orphan")
    items = db.relationship("PresupuestoItem", back_populates="presupuesto", cascade="all, delete-orphan")

    @property
    def costo_mano_obra(self):
        if self.modo_mano_obra == "Por monto":
            return self.monto_fijo_mo or 0
        return (self.horas_mano_obra or 0) * (self.valor_hora or 0)

    @property
    def total_repuestos(self):
        return sum(i.subtotal for i in self.items)

    @property
    def total(self):
        return self.costo_mano_obra + self.total_repuestos

    @property
    def costo_materiales(self):
        return sum(i.subtotal_costo for i in self.items)

    @property
    def ganancia(self):
        return self.total - self.costo_materiales

    @property
    def editable(self):
        return self.estado in ("Borrador", "Enviado")

    @classmethod
    def proximo_numero(cls):
        ultimo = db.session.query(db.func.max(cls.id)).scalar()
        return max((ultimo or 0) + 1, 40000)


class PresupuestoTrabajo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    presupuesto_id = db.Column(db.Integer, db.ForeignKey("presupuesto.id"), nullable=False)
    descripcion = db.Column(db.String(300), nullable=False)

    presupuesto = db.relationship("Presupuesto", back_populates="trabajos")


class PresupuestoItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    presupuesto_id = db.Column(db.Integer, db.ForeignKey("presupuesto.id"), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey("repuesto.id"))
    costo_unitario = db.Column(db.Float, default=0)  # para calcular la ganancia
    descripcion = db.Column(db.String(300))
    cantidad = db.Column(db.Float, default=1, nullable=False)
    precio_unitario = db.Column(db.Float, default=0, nullable=False)

    presupuesto = db.relationship("Presupuesto", back_populates="items")
    repuesto = db.relationship("Repuesto")

    @property
    def subtotal(self):
        return (self.cantidad or 0) * (self.precio_unitario or 0)

    @property
    def subtotal_costo(self):
        return (self.cantidad or 0) * (self.costo_unitario or 0)


# ─────────────────────────────────── Ventas ─────────────────────────────────

METODOS_PAGO = ["Efectivo", "Transferencia", "Débito", "Crédito", "Mercado Pago"]


class Venta(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, default=date.today, nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"))
    ot_id = db.Column(db.Integer, db.ForeignKey("orden_trabajo.id"))
    metodo_pago = db.Column(db.String(30))
    tipo_comprobante = db.Column(db.String(10), default="X")
    link_comprobante = db.Column(db.String(300))

    cliente = db.relationship("Cliente")
    ot = db.relationship("OrdenTrabajo", back_populates="ventas")
    items = db.relationship("VentaItem", back_populates="venta", cascade="all, delete-orphan")

    @property
    def total(self):
        return sum(i.subtotal for i in self.items)

    @property
    def costo_total(self):
        return sum(i.subtotal_costo for i in self.items)

    @property
    def ganancia(self):
        return self.total - self.costo_total

    @property
    def detalle(self):
        """Qué se vendió: lo que decía la OT, o los renglones del mostrador."""
        if self.ot is not None and self.ot.detalle:
            return self.ot.detalle.strip()
        renglones = [i.descripcion or (i.repuesto.nombre if i.repuesto else "") for i in self.items]
        return " · ".join(r for r in renglones if r)


class VentaItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey("venta.id"), nullable=False)
    repuesto_id = db.Column(db.Integer, db.ForeignKey("repuesto.id"))
    descripcion = db.Column(db.String(300))
    cantidad = db.Column(db.Float, default=1, nullable=False)
    precio_unitario = db.Column(db.Float, default=0, nullable=False)
    costo_unitario = db.Column(db.Float, default=0)

    venta = db.relationship("Venta", back_populates="items")
    repuesto = db.relationship("Repuesto", back_populates="ventas")

    @property
    def subtotal(self):
        return (self.cantidad or 0) * (self.precio_unitario or 0)

    @property
    def subtotal_costo(self):
        return (self.cantidad or 0) * (self.costo_unitario or 0)
