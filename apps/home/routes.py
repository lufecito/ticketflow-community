# -*- encoding: utf-8 -*-

from datetime import datetime
import os
from functools import wraps
from pathlib import Path

from flask import redirect, render_template, request, url_for, abort, send_from_directory, jsonify
from flask_login import current_user, login_required
from sqlalchemy import or_

from apps import db
from apps.authentication.models import Users
from apps.authentication.util import hash_pass
from apps.home import blueprint
from apps.home.models import (Cliente, Comentario, Ticket, TicketSoporte,
                              ComentarioSoporte, HistorialTicketSoporte,
                              ActivoTI, LicenciaTI, ControlTI)


ESTADOS = ['Ingresado', 'En evaluación', 'En Proceso', 'Esperando Usuario',
           'Esperando Proveedor', 'Resuelto', 'Cerrado', 'Cancelado', 'Finalizado']
PRIORIDADES = ['Baja', 'Media', 'Alta', 'Critica']
CATEGORIAS = ['Accesos e identidad', 'Equipos y hardware', 'Software y aplicaciones',
              'Microsoft 365 y licencias', 'ERP y sistemas corporativos',
              'Redes y conectividad', 'Impresión y periféricos', 'Seguridad',
              'Datos, SQL y Power BI', 'Respaldo y recuperación',
              'Soporte a usuarios', 'Altas, bajas y cambios',
              'Mantenimiento preventivo', 'Proyecto TI',
              'No TI / infraestructura general']
MODALIDADES = ['Remota', 'Presencial', 'Híbrida']
SLA = {
    'Critica': (30, 240), 'Alta': (120, 480),
    'Media': (240, 960), 'Baja': (480, 2400),
}
ROLES = ['Administrador', 'Usuario', 'Cliente', 'Tecnico']
CLIENT_ROLES = ['Usuario', 'Cliente']
REPORTS_DIR = Path(os.getenv('REPORTS_DIR', Path(__file__).resolve().parents[2] / 'reports'))


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'Administrador':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol not in ['Administrador', 'Tecnico']:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


@blueprint.route('/index')
@login_required
def index():
    if current_user.rol in CLIENT_ROLES:
        return redirect(url_for('home_blueprint.soporte_tickets'))

    ticket_counts = {
        'ingresado': Ticket.query.filter_by(estado='Ingresado').count(),
        'en_proceso': Ticket.query.filter(Ticket.estado.in_(['En evaluación', 'En Proceso', 'Esperando Usuario', 'Esperando Proveedor'])).count(),
        'finalizado': Ticket.query.filter(Ticket.estado.in_(['Resuelto', 'Cerrado', 'Finalizado'])).count(),
    }
    soporte_counts = {
        'abierto': TicketSoporte.query.filter_by(estado='Abierto').count(),
        'en_proceso': TicketSoporte.query.filter_by(estado='En proceso').count(),
        'resuelto': TicketSoporte.query.filter_by(estado='Resuelto').count(),
        'cerrado': TicketSoporte.query.filter_by(estado='Cerrado').count(),
    }

    priority_labels = ['Baja', 'Media', 'Alta', 'Critica']
    priority_counts = [
        {
            'label': prioridad,
            'total': (
                Ticket.query.filter_by(prioridad=prioridad).count()
                + TicketSoporte.query.filter_by(prioridad=prioridad).count()
            ),
        }
        for prioridad in priority_labels
    ]

    state_counts = [
        {'label': 'Ingresados', 'total': ticket_counts['ingresado']},
        {'label': 'En proceso', 'total': ticket_counts['en_proceso'] + soporte_counts['en_proceso']},
        {'label': 'Abiertos soporte', 'total': soporte_counts['abierto']},
        {'label': 'Resueltos/Cerrados', 'total': ticket_counts['finalizado'] + soporte_counts['resuelto'] + soporte_counts['cerrado']},
    ]

    latest_client_tickets = [
        {
            'id': ticket.id,
            'numero': ticket.numero,
            'asunto': ticket.asunto,
            'origen': 'Cliente',
            'solicitante': ticket.cliente.nombre if ticket.cliente else '-',
            'estado': ticket.estado,
            'prioridad': ticket.prioridad,
            'responsable': ticket.tecnico.username if ticket.tecnico else '-',
            'fecha': ticket.fecha_creacion,
            'url': url_for('home_blueprint.ticket_detalle', ticket_id=ticket.id),
        }
        for ticket in Ticket.query.order_by(Ticket.fecha_creacion.desc()).limit(8).all()
    ]
    latest_support_tickets = [
        {
            'id': ticket.id,
            'numero': ticket.numero,
            'asunto': ticket.asunto,
            'origen': 'Soporte',
            'solicitante': ticket.usuario.username if ticket.usuario else '-',
            'estado': ticket.estado,
            'prioridad': ticket.prioridad,
            'responsable': ticket.tecnico.username if ticket.tecnico else '-',
            'fecha': ticket.fecha_creacion,
            'url': url_for('home_blueprint.soporte_ticket_detalle', ticket_id=ticket.id),
        }
        for ticket in TicketSoporte.query.order_by(TicketSoporte.fecha_creacion.desc()).limit(8).all()
    ]
    ultimos_tickets = sorted(
        latest_client_tickets + latest_support_tickets,
        key=lambda item: item['fecha'],
        reverse=True,
    )[:8]

    stats = {
        'total_tickets': Ticket.query.count() + TicketSoporte.query.count(),
        'abiertos': ticket_counts['ingresado'] + soporte_counts['abierto'],
        'pendientes': ticket_counts['en_proceso'] + soporte_counts['en_proceso'],
        'cerrados': ticket_counts['finalizado'] + soporte_counts['resuelto'] + soporte_counts['cerrado'],
        'clientes_activos': Cliente.query.filter_by(activo=True).count(),
        'responsables_activos': Users.query.filter(
            Users.activo.is_(True),
            Users.rol.in_(['Administrador', 'Tecnico']),
        ).count(),
    }
    periodo_inicio, periodo_fin = _periodo_seleccionado(request.args.get('periodo'))
    periodos = _resumen_periodos(12)
    gestion_stats = _metricas_periodo(periodo_inicio, periodo_fin)

    return render_template(
        'home/index.html',
        segment='index',
        stats=stats,
        ultimos_tickets=ultimos_tickets,
        priority_counts=priority_counts,
        state_counts=state_counts,
        chart_labels=[item['label_corto'] for item in reversed(periodos[:6])],
        chart_values=[item['recibidos'] for item in reversed(periodos[:6])],
        gestion_stats=gestion_stats,
        periodo_inicio=periodo_inicio,
        periodo_fin=periodo_fin,
        periodos=periodos,
    )


@blueprint.route('/clientes')
@login_required
@staff_required
def clientes():
    buscar = request.args.get('buscar', '').strip()
    query = Cliente.query
    if buscar:
        like = f'%{buscar}%'
        query = query.filter(
            or_(
                Cliente.nombre.ilike(like),
                Cliente.rut.ilike(like),
                Cliente.correo.ilike(like),
                Cliente.ciudad.ilike(like),
            )
        )

    return render_template(
        'home/clientes.html',
        segment='clientes',
        clientes=query.order_by(Cliente.nombre.asc()).all(),
        buscar=buscar,
    )


@blueprint.route('/clientes/nuevo', methods=['GET', 'POST'])
@blueprint.route('/clientes/<int:cliente_id>/editar', methods=['GET', 'POST'])
@login_required
@staff_required
def cliente_form(cliente_id=None):
    cliente = Cliente.query.get_or_404(cliente_id) if cliente_id else Cliente()
    if request.method == 'POST':
        _llenar_cliente(cliente, request.form)
        db.session.add(cliente)
        db.session.commit()
        return redirect(url_for('home_blueprint.clientes'))

    return render_template('home/cliente_form.html', segment='clientes', cliente=cliente)


@blueprint.route('/clientes/<int:cliente_id>/eliminar', methods=['POST'])
@login_required
@staff_required
def cliente_eliminar(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    db.session.delete(cliente)
    db.session.commit()
    return redirect(url_for('home_blueprint.clientes'))


@blueprint.route('/tickets')
@login_required
@staff_required
def tickets():
    estado = request.args.get('estado', '').strip()
    prioridad = request.args.get('prioridad', '').strip()
    cliente_id = request.args.get('cliente_id', '').strip()
    buscar = request.args.get('buscar', '').strip()
    categoria = request.args.get('categoria', '').strip()
    periodo = request.args.get('periodo', '').strip()
    filtros = {
        'estado': estado,
        'prioridad': prioridad,
        'cliente_id': cliente_id,
        'buscar': buscar,
        'categoria': categoria,
        'periodo': periodo,
    }

    query = Ticket.query
    periodo_inicio = periodo_fin = None
    if periodo:
        periodo_inicio, periodo_fin = _periodo_seleccionado(periodo)
        fecha_ingreso = db.func.coalesce(Ticket.fecha_solicitud, Ticket.fecha_creacion)
        query = query.filter(fecha_ingreso >= periodo_inicio, fecha_ingreso < periodo_fin)
    if estado:
        query = query.filter_by(estado=estado)
    if prioridad:
        query = query.filter_by(prioridad=prioridad)
    if cliente_id:
        query = query.filter_by(cliente_id=cliente_id)
    if buscar:
        like = f'%{buscar}%'
        query = query.filter(or_(Ticket.numero.ilike(like), Ticket.asunto.ilike(like)))
    if categoria:
        query = query.filter_by(categoria=categoria)

    return render_template(
        'home/tickets.html',
        segment='tickets',
        tickets=query.order_by(Ticket.fecha_creacion.desc()).all(),
        clientes=Cliente.query.order_by(Cliente.nombre.asc()).all(),
        estados=ESTADOS,
        prioridades=PRIORIDADES,
        categorias=CATEGORIAS,
        filtros=filtros,
        periodo_inicio=periodo_inicio,
        periodo_fin=periodo_fin,
    )


@blueprint.route('/tablero-kanban')
@login_required
@staff_required
def tablero_kanban():
    tickets_list = Ticket.query.order_by(Ticket.fecha_actualizacion.desc()).all()
    columnas = [
        {'id': 'pendiente', 'titulo': 'Pendiente', 'estado_destino': 'Ingresado', 'estados': ['Ingresado']},
        {'id': 'en-proceso', 'titulo': 'En proceso', 'estado_destino': 'En Proceso', 'estados': ['En Proceso', 'Esperando Usuario', 'Esperando Proveedor']},
        {'id': 'resuelto', 'titulo': 'Resuelto', 'estado_destino': 'Resuelto', 'estados': ['Resuelto']},
        {'id': 'cerrado', 'titulo': 'Cerrado', 'estado_destino': 'Cerrado', 'estados': ['Cerrado', 'Finalizado', 'Cancelado']},
    ]
    for columna in columnas:
        columna['tickets'] = [ticket for ticket in tickets_list if ticket.estado in columna['estados']]
    clasificados = {estado for columna in columnas for estado in columna['estados']}
    columnas[0]['tickets'].extend(ticket for ticket in tickets_list if ticket.estado not in clasificados)
    return render_template(
        'home/tablero_kanban.html', segment='tablero_kanban', columnas=columnas,
        prioridades=PRIORIDADES,
        tecnicos=Users.query.filter_by(activo=True).order_by(Users.username.asc()).all(),
        total_tickets=len(tickets_list),
    )


@blueprint.route('/tablero-kanban/tickets/<int:ticket_id>/estado', methods=['POST'])
@login_required
@staff_required
def tablero_kanban_estado(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    nuevo_estado = (request.get_json(silent=True) or {}).get('estado', '').strip()
    if nuevo_estado not in ['Ingresado', 'En Proceso', 'Resuelto', 'Cerrado']:
        return jsonify({'ok': False, 'error': 'Estado no permitido'}), 400
    estado_anterior = ticket.estado
    ahora = datetime.utcnow()
    ticket.estado = nuevo_estado
    ticket.fecha_actualizacion = ahora
    if nuevo_estado == 'En Proceso' and not ticket.fecha_primera_atencion:
        ticket.fecha_primera_atencion = ahora
    if nuevo_estado == 'Resuelto' and not ticket.fecha_resolucion:
        ticket.fecha_resolucion = ahora
    if nuevo_estado == 'Cerrado':
        ticket.fecha_resolucion = ticket.fecha_resolucion or ahora
        ticket.fecha_cierre = ahora
    elif estado_anterior in ('Cerrado', 'Finalizado'):
        ticket.fecha_cierre = None
    db.session.commit()
    return jsonify({'ok': True, 'ticket': ticket.numero, 'estado': ticket.estado})


@blueprint.route('/tickets/nuevo', methods=['GET', 'POST'])
@blueprint.route('/tickets/<int:ticket_id>/editar', methods=['GET', 'POST'])
@login_required
@staff_required
def ticket_form(ticket_id=None):
    ticket = Ticket.query.get_or_404(ticket_id) if ticket_id else Ticket(numero=_siguiente_numero_ticket())
    if request.method == 'POST':
        _llenar_ticket(ticket, request.form)
        db.session.add(ticket)
        db.session.commit()
        return redirect(url_for('home_blueprint.ticket_detalle', ticket_id=ticket.id))

    return render_template(
        'home/ticket_form.html',
        segment='tickets',
        ticket=ticket,
        clientes=Cliente.query.order_by(Cliente.nombre.asc()).all(),
        tecnicos=Users.query.filter_by(activo=True).order_by(Users.username.asc()).all(),
        estados=ESTADOS,
        prioridades=PRIORIDADES,
        categorias=CATEGORIAS,
        modalidades=MODALIDADES,
    )


@blueprint.route('/tickets/<int:ticket_id>')
@login_required
@staff_required
def ticket_detalle(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    return render_template('home/ticket_detalle.html', segment='tickets', ticket=ticket, estados=ESTADOS)


@blueprint.route('/tickets/<int:ticket_id>/estado', methods=['POST'])
@login_required
@staff_required
def ticket_estado(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    estado_anterior = ticket.estado
    ticket.estado = request.form.get('estado', ticket.estado)
    ahora = datetime.utcnow()
    ticket.fecha_actualizacion = ahora
    if ticket.estado in ('En evaluación', 'En Proceso') and not ticket.fecha_primera_atencion:
        ticket.fecha_primera_atencion = ahora
    if ticket.estado == 'Resuelto' and not ticket.fecha_resolucion:
        ticket.fecha_resolucion = ahora
    if ticket.estado in ('Cerrado', 'Finalizado'):
        ticket.fecha_resolucion = ticket.fecha_resolucion or ahora
        ticket.fecha_cierre = ahora
    elif estado_anterior in ('Cerrado', 'Finalizado'):
        ticket.fecha_cierre = None
    db.session.commit()
    return redirect(url_for('home_blueprint.ticket_detalle', ticket_id=ticket.id))


@blueprint.route('/tickets/<int:ticket_id>/comentarios', methods=['POST'])
@login_required
@staff_required
def ticket_comentario(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    texto = request.form.get('comentario', '').strip()
    if texto:
        db.session.add(Comentario(ticket=ticket, usuario=current_user, comentario=texto))
        ticket.fecha_actualizacion = datetime.utcnow()
        db.session.commit()
    return redirect(url_for('home_blueprint.ticket_detalle', ticket_id=ticket.id))


@blueprint.route('/tickets/<int:ticket_id>/eliminar', methods=['POST'])
@login_required
@staff_required
def ticket_eliminar(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    db.session.delete(ticket)
    db.session.commit()
    return redirect(url_for('home_blueprint.tickets'))


@blueprint.route('/usuarios')
@login_required
@admin_required
def usuarios():
    buscar = request.args.get('buscar', '').strip()
    query = Users.query
    if buscar:
        like = f'%{buscar}%'
        query = query.filter(or_(Users.username.ilike(like), Users.email.ilike(like), Users.nombre.ilike(like)))

    return render_template(
        'home/usuarios.html',
        segment='usuarios',
        usuarios=query.order_by(Users.username.asc()).all(),
        buscar=buscar,
    )


@blueprint.route('/usuarios/nuevo', methods=['GET', 'POST'])
@blueprint.route('/usuarios/<int:usuario_id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def usuario_form(usuario_id=None):
    usuario = Users.query.get_or_404(usuario_id) if usuario_id else Users()
    if request.method == 'POST':
        _llenar_usuario(usuario, request.form, crear=usuario_id is None)
        db.session.add(usuario)
        db.session.commit()
        return redirect(url_for('home_blueprint.usuarios'))

    return render_template('home/usuario_form.html', segment='usuarios', usuario=usuario, roles=ROLES)


@blueprint.route('/usuarios/<int:usuario_id>/eliminar', methods=['POST'])
@login_required
@admin_required
def usuario_eliminar(usuario_id):
    usuario = Users.query.get_or_404(usuario_id)
    db.session.delete(usuario)
    db.session.commit()
    return redirect(url_for('home_blueprint.usuarios'))


@blueprint.route('/configuracion', methods=['GET', 'POST'])
@login_required
@admin_required
def configuracion():
    config = {
        'nombre_empresa': 'Ticket Kanban',
        'correo': '',
        'telefono': '',
        'tema': 'CoreUI',
    }
    if request.method == 'POST':
        config.update({
            'nombre_empresa': request.form.get('nombre_empresa', '').strip(),
            'correo': request.form.get('correo', '').strip(),
            'telefono': request.form.get('telefono', '').strip(),
            'tema': request.form.get('tema', 'CoreUI').strip(),
        })
        return render_template('home/configuracion.html', segment='configuracion', config=config, guardado=True)

    return render_template('home/configuracion.html', segment='configuracion', config=config)


@blueprint.route('/gobierno-ti', methods=['GET', 'POST'])
@login_required
@staff_required
def gobierno_ti():
    if request.method == 'POST':
        tipo = request.form.get('tipo_registro')
        if tipo == 'activo':
            db.session.add(ActivoTI(
                codigo=request.form.get('codigo', '').strip(),
                tipo=request.form.get('tipo', '').strip(),
                marca=request.form.get('marca', '').strip(),
                modelo=request.form.get('modelo', '').strip(),
                serie=request.form.get('serie', '').strip(),
                sede=request.form.get('sede', '').strip(),
                responsable=request.form.get('responsable', '').strip(),
                estado=request.form.get('estado', 'Operativo'),
                proximo_mantenimiento=_parse_date(request.form.get('proximo_mantenimiento')),
            ))
        elif tipo == 'licencia':
            db.session.add(LicenciaTI(
                producto=request.form.get('producto', '').strip(),
                cuenta=request.form.get('cuenta', '').strip(),
                responsable=request.form.get('responsable', '').strip(),
                cantidad=int(request.form.get('cantidad') or 1),
                costo_mensual=_float_or_zero(request.form.get('costo_mensual')),
                vencimiento=_parse_date(request.form.get('vencimiento')),
                estado=request.form.get('estado', 'Activa'),
            ))
        elif tipo == 'control':
            db.session.add(ControlTI(
                tipo=request.form.get('tipo', '').strip(),
                nombre=request.form.get('nombre', '').strip(),
                frecuencia=request.form.get('frecuencia', '').strip(),
                responsable=request.form.get('responsable', '').strip(),
                ultima_ejecucion=_parse_date(request.form.get('ultima_ejecucion')),
                proxima_ejecucion=_parse_date(request.form.get('proxima_ejecucion')),
                estado=request.form.get('estado', 'Pendiente'),
                observaciones=request.form.get('observaciones', '').strip(),
            ))
        db.session.commit()
        return redirect(url_for('home_blueprint.gobierno_ti'))
    return render_template(
        'home/gobierno_ti.html', segment='gobierno_ti',
        activos=ActivoTI.query.order_by(ActivoTI.codigo).all(),
        licencias=LicenciaTI.query.order_by(LicenciaTI.producto).all(),
        controles=ControlTI.query.order_by(ControlTI.proxima_ejecucion).all(),
    )


@blueprint.route('/gobierno-ti/<string:tipo>/<int:registro_id>/eliminar', methods=['POST'])
@login_required
@admin_required
def gobierno_ti_eliminar(tipo, registro_id):
    modelos = {'activo': ActivoTI, 'licencia': LicenciaTI, 'control': ControlTI}
    modelo = modelos.get(tipo)
    if not modelo:
        abort(404)
    db.session.delete(modelo.query.get_or_404(registro_id))
    db.session.commit()
    return redirect(url_for('home_blueprint.gobierno_ti'))


@blueprint.route('/reportes')
@login_required
@staff_required
def reportes():
    archivos=[]
    if REPORTS_DIR.exists():
        for path in sorted(REPORTS_DIR.glob('informe_gestion_*.*'), reverse=True):
            if path.suffix.lower() in ('.pdf', '.csv'):
                archivos.append({'nombre':path.name,'formato':path.suffix[1:].upper(),'tamano':path.stat().st_size,'fecha':datetime.fromtimestamp(path.stat().st_mtime)})
    return render_template('home/reportes.html',segment='reportes',archivos=archivos)


@blueprint.route('/reportes/descargar/<path:filename>')
@login_required
@staff_required
def reporte_descargar(filename):
    if Path(filename).name != filename or not filename.startswith('informe_gestion_'):
        abort(404)
    return send_from_directory(str(REPORTS_DIR),filename,as_attachment=True)


def _llenar_cliente(cliente, form):
    cliente.nombre = form.get('nombre', '').strip()
    cliente.rut = form.get('rut', '').strip()
    cliente.direccion = form.get('direccion', '').strip()
    cliente.ciudad = form.get('ciudad', '').strip()
    cliente.telefono = form.get('telefono', '').strip()
    cliente.correo = form.get('correo', '').strip()
    cliente.activo = form.get('activo') == 'on'


def _llenar_ticket(ticket, form):
    ticket.cliente_id = form.get('cliente_id')
    ticket.asunto = form.get('asunto', '').strip()
    ticket.descripcion = form.get('descripcion', '').strip()
    ticket.estado = form.get('estado', 'Ingresado')
    ticket.prioridad = form.get('prioridad', 'Media')
    ticket.categoria = form.get('categoria', 'Soporte a usuarios')
    ticket.subcategoria = form.get('subcategoria', '').strip()
    ticket.modalidad = form.get('modalidad', 'Remota')
    ticket.activo_referencia = form.get('activo_referencia', '').strip()
    ticket.diagnostico = form.get('diagnostico', '').strip()
    ticket.solucion = form.get('solucion', '').strip()
    ticket.horas_efectivas = _float_or_zero(form.get('horas_efectivas'))
    ticket.validacion_usuario = form.get('validacion_usuario') == 'on'
    ticket.fecha_solicitud = _parse_datetime(form.get('fecha_solicitud')) or ticket.fecha_solicitud or datetime.utcnow()
    ticket.fecha_primera_atencion = _parse_datetime(form.get('fecha_primera_atencion'))
    ticket.fecha_resolucion = _parse_datetime(form.get('fecha_resolucion'))
    ticket.sla_primera_minutos, ticket.sla_resolucion_minutos = SLA.get(ticket.prioridad, SLA['Media'])
    ticket.tecnico_id = form.get('tecnico_id') or None
    ticket.fecha_actualizacion = datetime.utcnow()
    if ticket.estado in ('Cerrado', 'Finalizado'):
        ticket.fecha_resolucion = ticket.fecha_resolucion or datetime.utcnow()
        ticket.fecha_cierre = ticket.fecha_cierre or datetime.utcnow()


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    parsed = _parse_datetime(value)
    return parsed.date() if parsed else None


def _float_or_zero(value):
    try:
        return max(0, float(str(value or '0').replace(',', '.')))
    except ValueError:
        return 0


def _llenar_usuario(usuario, form, crear=False):
    usuario.username = form.get('username', '').strip()
    usuario.email = form.get('email', '').strip()
    usuario.nombre = form.get('nombre', '').strip()
    usuario.apellido = form.get('apellido', '').strip()
    usuario.rol = form.get('rol', 'Tecnico')
    usuario.activo = form.get('activo') == 'on'
    password = form.get('password', '').strip()
    if crear or password:
        usuario.password = hash_pass(password)


def _siguiente_numero_ticket():
    ultimo = Ticket.query.order_by(Ticket.id.desc()).first()
    siguiente = (ultimo.id + 1) if ultimo else 1
    return f'TK-{siguiente:05d}'


def _tickets_por_mes():
    meses = []
    ahora = datetime.utcnow()
    for offset in range(5, -1, -1):
        year = ahora.year
        month = ahora.month - offset
        while month <= 0:
            month += 12
            year -= 1
        total = Ticket.query.filter(
            db.extract('year', Ticket.fecha_creacion) == year,
            db.extract('month', Ticket.fecha_creacion) == month,
        ).count() + TicketSoporte.query.filter(
            db.extract('year', TicketSoporte.fecha_creacion) == year,
            db.extract('month', TicketSoporte.fecha_creacion) == month,
        ).count()
        meses.append({'mes': f'{month:02d}/{year}', 'total': total})
    return meses


def _mover_mes(fecha, meses):
    indice = fecha.year * 12 + fecha.month - 1 + meses
    return datetime(indice // 12, indice % 12 + 1, 15)


def _periodo_actual(referencia=None):
    referencia = referencia or datetime.utcnow()
    inicio = datetime(referencia.year, referencia.month, 15)
    if referencia < inicio:
        inicio = _mover_mes(inicio, -1)
    return inicio, _mover_mes(inicio, 1)


def _periodo_seleccionado(valor):
    if valor:
        try:
            inicio = datetime.strptime(valor, '%Y-%m-%d')
            if inicio.day == 15:
                return inicio, _mover_mes(inicio, 1)
        except ValueError:
            pass
    return _periodo_actual()


def _metricas_periodo(inicio, fin):
    fecha_ingreso = db.func.coalesce(Ticket.fecha_solicitud, Ticket.fecha_creacion)
    fecha_salida = db.func.coalesce(Ticket.fecha_resolucion, Ticket.fecha_cierre)
    recibidos = Ticket.query.filter(fecha_ingreso >= inicio, fecha_ingreso < fin).all()
    resueltos = Ticket.query.filter(fecha_salida >= inicio, fecha_salida < fin).all()
    primera_medidos = [t for t in recibidos if t.sla_primera_cumplido is not None]
    resolucion_medidos = [t for t in recibidos if t.sla_resolucion_cumplido is not None]
    horas = sum(t.horas_efectivas or 0 for t in resueltos)
    costo = sum((t.valor_estimado or 0) if (t.valor_estimado or 0) > 0 else (t.horas_efectivas or 0) * 36700 for t in resueltos)
    return {
        'volumen': len(recibidos), 'resueltos': len(resueltos), 'horas': horas,
        'costo': costo,
        'sla_primera': round(100 * sum(t.sla_primera_cumplido for t in primera_medidos) / len(primera_medidos)) if primera_medidos else None,
        'sla_resolucion': round(100 * sum(t.sla_resolucion_cumplido for t in resolucion_medidos) / len(resolucion_medidos)) if resolucion_medidos else None,
    }


def _resumen_periodos(cantidad=12, referencia=None):
    inicio_actual, _ = _periodo_actual(referencia)
    periodos = []
    for offset in range(cantidad):
        inicio = _mover_mes(inicio_actual, -offset)
        fin = _mover_mes(inicio, 1)
        metricas = _metricas_periodo(inicio, fin)
        periodos.append({
            'inicio': inicio, 'fin': fin,
            'valor': inicio.strftime('%Y-%m-%d'),
            'label': f'{inicio.strftime("%d/%m/%Y")} - {fin.strftime("%d/%m/%Y")}',
            'label_corto': f'{inicio.strftime("%d/%m")} - {fin.strftime("%d/%m")}',
            'recibidos': metricas['volumen'],
            **metricas,
        })
    return periodos


def _siguiente_numero_soporte():
    ultimo = TicketSoporte.query.order_by(TicketSoporte.id.desc()).first()
    siguiente = (ultimo.id + 1) if ultimo else 1
    return f'TS-{siguiente:05d}'


# Support Tickets Module

@blueprint.route('/soporte/tickets')
@login_required
def soporte_tickets():
    estado = request.args.get('estado', '').strip()
    prioridad = request.args.get('prioridad', '').strip()
    usuario_id = request.args.get('usuario_id', '').strip()
    fecha_str = request.args.get('fecha', '').strip()
    buscar = request.args.get('buscar', '').strip()
    filtros = {
        'estado': estado,
        'prioridad': prioridad,
        'usuario_id': usuario_id,
        'fecha': fecha_str,
        'buscar': buscar,
    }

    query = TicketSoporte.query

    # RBAC: Users only see their own support tickets.
    if current_user.rol in CLIENT_ROLES:
        query = query.filter_by(usuario_id=current_user.id)
    else:
        # Administrators / staff can filter by user
        if usuario_id:
            query = query.filter_by(usuario_id=usuario_id)

    if estado:
        query = query.filter_by(estado=estado)
    if prioridad:
        query = query.filter_by(prioridad=prioridad)
    if fecha_str:
        try:
            fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')
            query = query.filter(db.func.date(TicketSoporte.fecha_creacion) == fecha_obj.date())
        except ValueError:
            pass
    if buscar:
        like = f'%{buscar}%'
        query = query.filter(or_(TicketSoporte.numero.ilike(like), TicketSoporte.asunto.ilike(like)))

    tickets_list = query.order_by(TicketSoporte.fecha_creacion.desc()).all()
    
    # We also need list of users for administrator filters
    usuarios_filtro = Users.query.order_by(Users.username.asc()).all() if current_user.rol == 'Administrador' else []

    return render_template(
        'home/soporte_tickets.html',
        segment='soporte_tickets',
        tickets=tickets_list,
        usuarios=usuarios_filtro,
        estados_soporte=['Abierto', 'En proceso', 'Resuelto', 'Cerrado'],
        prioridades=PRIORIDADES,
        filtros=filtros,
    )


@blueprint.route('/soporte/tickets/nuevo', methods=['GET', 'POST'])
@login_required
def soporte_ticket_nuevo():
    if request.method == 'POST':
        asunto = request.form.get('asunto', '').strip()
        categoria = request.form.get('categoria', '').strip()
        prioridad = request.form.get('prioridad', 'Media').strip()
        descripcion = request.form.get('descripcion', '').strip()

        if not asunto or not categoria:
            return render_template(
                'home/soporte_ticket_form.html',
                segment='soporte_tickets',
                msg='Asunto y Categoría son campos obligatorios',
                prioridades=PRIORIDADES,
            )

        ticket = TicketSoporte(
            numero=_siguiente_numero_soporte(),
            usuario_id=current_user.id,
            asunto=asunto,
            categoria=categoria,
            prioridad=prioridad,
            descripcion=descripcion,
            estado='Abierto'
        )
        db.session.add(ticket)
        db.session.commit()

        # Log initial history
        historial = HistorialTicketSoporte(
            ticket_id=ticket.id,
            usuario_id=current_user.id,
            campo_modificado='Creado',
            valor_anterior='',
            valor_nuevo=f'Ticket creado con estado Abierto'
        )
        db.session.add(historial)
        db.session.commit()

        return redirect(url_for('home_blueprint.soporte_ticket_detalle', ticket_id=ticket.id))

    return render_template(
        'home/soporte_ticket_form.html',
        segment='soporte_tickets',
        prioridades=PRIORIDADES,
    )


@blueprint.route('/soporte/tickets/<int:ticket_id>')
@login_required
def soporte_ticket_detalle(ticket_id):
    ticket = TicketSoporte.query.get_or_404(ticket_id)

    # RBAC: normal users can only view their own support tickets
    if current_user.rol in CLIENT_ROLES and ticket.usuario_id != current_user.id:
        abort(403)

    # For assigning responsibles, get a list of admins and technicians
    tecnicos = Users.query.filter(Users.rol.in_(['Administrador', 'Tecnico'])).filter_by(activo=True).order_by(Users.username.asc()).all()

    return render_template(
        'home/soporte_ticket_detalle.html',
        segment='soporte_tickets',
        ticket=ticket,
        tecnicos=tecnicos,
        estados_soporte=['Abierto', 'En proceso', 'Resuelto', 'Cerrado'],
    )


@blueprint.route('/soporte/tickets/<int:ticket_id>/comentario', methods=['POST'])
@login_required
def soporte_ticket_comentario(ticket_id):
    ticket = TicketSoporte.query.get_or_404(ticket_id)

    if current_user.rol in CLIENT_ROLES and ticket.usuario_id != current_user.id:
        abort(403)

    # Rule: "Agregar comentarios mientras el ticket permanezca abierto"
    if ticket.estado == 'Cerrado' and current_user.rol != 'Administrador':
        return redirect(url_for('home_blueprint.soporte_ticket_detalle', ticket_id=ticket.id))

    texto = request.form.get('comentario', '').strip()
    if texto:
        comentario = ComentarioSoporte(
            ticket=ticket,
            usuario=current_user,
            comentario=texto
        )
        ticket.fecha_actualizacion = datetime.utcnow()
        db.session.add(comentario)
        db.session.commit()

    return redirect(url_for('home_blueprint.soporte_ticket_detalle', ticket_id=ticket.id))


@blueprint.route('/soporte/tickets/<int:ticket_id>/actualizar', methods=['POST'])
@login_required
@admin_required
def soporte_ticket_actualizar(ticket_id):
    ticket = TicketSoporte.query.get_or_404(ticket_id)
    
    nuevo_estado = request.form.get('estado', '').strip()
    nuevo_tecnico_id = request.form.get('tecnico_id', '').strip()
    nueva_observacion = request.form.get('observacion_interna', '').strip()

    cambios = False

    # Check for state change
    if nuevo_estado and nuevo_estado != ticket.estado:
        historial = HistorialTicketSoporte(
            ticket_id=ticket.id,
            usuario_id=current_user.id,
            campo_modificado='Estado',
            valor_anterior=ticket.estado,
            valor_nuevo=nuevo_estado
        )
        ticket.estado = nuevo_estado
        ticket.fecha_actualizacion = datetime.utcnow()
        if nuevo_estado == 'Cerrado':
            ticket.fecha_cierre = datetime.utcnow()
        else:
            ticket.fecha_cierre = None
        db.session.add(historial)
        cambios = True

    # Check for responsible change
    original_tecnico_id = str(ticket.tecnico_id) if ticket.tecnico_id else ''
    if nuevo_tecnico_id != original_tecnico_id:
        nombre_anterior = ticket.tecnico.username if ticket.tecnico else 'Ninguno'
        
        if nuevo_tecnico_id:
            nuevo_tecnico = Users.query.get(int(nuevo_tecnico_id))
            ticket.tecnico_id = nuevo_tecnico.id
            nombre_nuevo = nuevo_tecnico.username
        else:
            ticket.tecnico_id = None
            nombre_nuevo = 'Ninguno'
            
        historial = HistorialTicketSoporte(
            ticket_id=ticket.id,
            usuario_id=current_user.id,
            campo_modificado='Responsable',
            valor_anterior=nombre_anterior,
            valor_nuevo=nombre_nuevo
        )
        ticket.fecha_actualizacion = datetime.utcnow()
        db.session.add(historial)
        cambios = True

    # Update internal observation
    if nueva_observacion != (ticket.observacion_interna or ''):
        historial = HistorialTicketSoporte(
            ticket_id=ticket.id,
            usuario_id=current_user.id,
            campo_modificado='Observación Interna',
            valor_anterior='Actualizado' if ticket.observacion_interna else 'Creado',
            valor_nuevo='Nueva observación agregada'
        )
        ticket.observacion_interna = nueva_observacion
        ticket.fecha_actualizacion = datetime.utcnow()
        db.session.add(historial)
        cambios = True

    if cambios:
        db.session.commit()

    return redirect(url_for('home_blueprint.soporte_ticket_detalle', ticket_id=ticket.id))
