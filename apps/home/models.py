# -*- encoding: utf-8 -*-

from datetime import datetime

from apps import db


class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    rut = db.Column(db.String(20), unique=True)
    direccion = db.Column(db.String(200))
    ciudad = db.Column(db.String(80))
    telefono = db.Column(db.String(40))
    correo = db.Column(db.String(120))
    activo = db.Column(db.Boolean, default=True, nullable=False)

    tickets = db.relationship('Ticket', back_populates='cliente', lazy=True)


class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    asunto = db.Column(db.String(160), nullable=False)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(30), default='Ingresado', nullable=False)
    prioridad = db.Column(db.String(30), default='Media', nullable=False)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    fecha_cierre = db.Column(db.DateTime)
    fecha_solicitud = db.Column(db.DateTime)
    fecha_primera_atencion = db.Column(db.DateTime)
    fecha_resolucion = db.Column(db.DateTime)
    horas_efectivas = db.Column(db.Float, default=0, nullable=False)
    valor_estimado = db.Column(db.Float, default=0, nullable=False)
    modalidad = db.Column(db.String(20), default='Remota', nullable=False)
    categoria = db.Column(db.String(60), default='Soporte a usuarios', nullable=False)
    subcategoria = db.Column(db.String(80))
    activo_referencia = db.Column(db.String(120))
    diagnostico = db.Column(db.Text)
    solucion = db.Column(db.Text)
    validacion_usuario = db.Column(db.Boolean, default=False, nullable=False)
    sla_primera_minutos = db.Column(db.Integer)
    sla_resolucion_minutos = db.Column(db.Integer)

    cliente = db.relationship('Cliente', back_populates='tickets')
    tecnico = db.relationship('Users', foreign_keys=[tecnico_id])
    comentarios = db.relationship('Comentario', back_populates='ticket', cascade='all, delete-orphan', lazy=True)

    @property
    def sla_primera_cumplido(self):
        if not self.fecha_primera_atencion or not self.fecha_solicitud or not self.sla_primera_minutos:
            return None
        return (self.fecha_primera_atencion - self.fecha_solicitud).total_seconds() <= self.sla_primera_minutos * 60

    @property
    def sla_resolucion_cumplido(self):
        if not self.fecha_resolucion or not self.fecha_solicitud or not self.sla_resolucion_minutos:
            return None
        return (self.fecha_resolucion - self.fecha_solicitud).total_seconds() <= self.sla_resolucion_minutos * 60


class Comentario(db.Model):
    __tablename__ = 'comentarios'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    comentario = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    ticket = db.relationship('Ticket', back_populates='comentarios')
    usuario = db.relationship('Users')


class TicketSoporte(db.Model):
    __tablename__ = 'tickets_soporte'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    asunto = db.Column(db.String(160), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    prioridad = db.Column(db.String(30), default='Media', nullable=False)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(30), default='Abierto', nullable=False)
    tecnico_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    observacion_interna = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    fecha_cierre = db.Column(db.DateTime)

    usuario = db.relationship('Users', foreign_keys=[usuario_id])
    tecnico = db.relationship('Users', foreign_keys=[tecnico_id])
    comentarios = db.relationship('ComentarioSoporte', back_populates='ticket', cascade='all, delete-orphan', lazy=True)
    historial = db.relationship('HistorialTicketSoporte', back_populates='ticket', cascade='all, delete-orphan', lazy=True)


class ComentarioSoporte(db.Model):
    __tablename__ = 'comentarios_soporte'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets_soporte.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    comentario = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    ticket = db.relationship('TicketSoporte', back_populates='comentarios')
    usuario = db.relationship('Users')


class HistorialTicketSoporte(db.Model):
    __tablename__ = 'historial_tickets_soporte'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets_soporte.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    campo_modificado = db.Column(db.String(50), nullable=False)
    valor_anterior = db.Column(db.String(200))
    valor_nuevo = db.Column(db.String(200))
    fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    ticket = db.relationship('TicketSoporte', back_populates='historial')
    usuario = db.relationship('Users')


class ActivoTI(db.Model):
    __tablename__ = 'activos_ti'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), unique=True, nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    marca = db.Column(db.String(60))
    modelo = db.Column(db.String(80))
    serie = db.Column(db.String(100))
    sede = db.Column(db.String(80))
    responsable = db.Column(db.String(120))
    estado = db.Column(db.String(30), default='Operativo', nullable=False)
    proximo_mantenimiento = db.Column(db.Date)
    activo = db.Column(db.Boolean, default=True, nullable=False)


class LicenciaTI(db.Model):
    __tablename__ = 'licencias_ti'
    id = db.Column(db.Integer, primary_key=True)
    producto = db.Column(db.String(100), nullable=False)
    cuenta = db.Column(db.String(120))
    responsable = db.Column(db.String(120))
    cantidad = db.Column(db.Integer, default=1, nullable=False)
    costo_mensual = db.Column(db.Float, default=0, nullable=False)
    vencimiento = db.Column(db.Date)
    estado = db.Column(db.String(30), default='Activa', nullable=False)


class ControlTI(db.Model):
    __tablename__ = 'controles_ti'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50), nullable=False)
    nombre = db.Column(db.String(140), nullable=False)
    frecuencia = db.Column(db.String(40), nullable=False)
    responsable = db.Column(db.String(120))
    ultima_ejecucion = db.Column(db.Date)
    proxima_ejecucion = db.Column(db.Date)
    estado = db.Column(db.String(30), default='Pendiente', nullable=False)
    observaciones = db.Column(db.Text)
