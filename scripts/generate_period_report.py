#!/usr/bin/env python3
import argparse
import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(os.getenv('TICKETFLOW_ROOT', Path(__file__).resolve().parents[1]))
DB = Path(os.getenv('SQLITE_PATH', ROOT / 'apps' / 'db.sqlite3'))
OUT = Path(os.getenv('REPORTS_DIR', ROOT / 'reports'))


def move_month(value, delta):
    index = value.year * 12 + value.month - 1 + delta
    return datetime(index // 12, index % 12 + 1, 15)


def previous_period(now=None):
    now = now or datetime.now()
    current_cut = datetime(now.year, now.month, 15)
    end = current_cut if now >= current_cut else move_month(current_cut, -1)
    return move_month(end, -1), end


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = landscape(A4)
    canvas.setFillColor(colors.HexColor('#9AA3AF'))
    canvas.setFont('Helvetica', 7.5)
    canvas.drawString(15*mm, height-10*mm, os.getenv('REPORT_HEADER', 'TicketFlow Community | Internal report'))
    canvas.setStrokeColor(colors.HexColor('#D8DEE7'))
    canvas.line(15*mm, height-13*mm, width-15*mm, height-13*mm)
    canvas.setFont('Helvetica', 7)
    canvas.drawRightString(width-15*mm, 9*mm, f'Página {doc.page}')
    canvas.restoreState()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', help='Inicio YYYY-MM-15; si se omite genera el período recién cerrado')
    args = parser.parse_args()
    if args.start:
        start = datetime.strptime(args.start, '%Y-%m-%d')
        if start.day != 15:
            raise SystemExit('El inicio debe ser día 15')
        end = move_month(start, 1)
    else:
        start, end = previous_period()

    OUT.mkdir(parents=True, exist_ok=True)
    stem = f'informe_gestion_{start:%Y-%m-%d}_a_{end:%Y-%m-%d}'
    pdf_path, csv_path = OUT / f'{stem}.pdf', OUT / f'{stem}.csv'
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    received = conn.execute('''
      SELECT t.*, c.nombre cliente, COALESCE(u.nombre || ' ' || u.apellido, u.username) tecnico
      FROM tickets t LEFT JOIN clientes c ON c.id=t.cliente_id LEFT JOIN usuarios u ON u.id=t.tecnico_id
      WHERE COALESCE(t.fecha_solicitud,t.fecha_creacion)>=? AND COALESCE(t.fecha_solicitud,t.fecha_creacion)<?
      ORDER BY COALESCE(t.fecha_solicitud,t.fecha_creacion)
    ''', (start, end)).fetchall()
    resolved = conn.execute('''
      SELECT t.*, c.nombre cliente, COALESCE(u.nombre || ' ' || u.apellido, u.username) tecnico
      FROM tickets t LEFT JOIN clientes c ON c.id=t.cliente_id LEFT JOIN usuarios u ON u.id=t.tecnico_id
      WHERE COALESCE(t.fecha_resolucion,t.fecha_cierre)>=? AND COALESCE(t.fecha_resolucion,t.fecha_cierre)<?
      ORDER BY COALESCE(t.fecha_resolucion,t.fecha_cierre)
    ''', (start, end)).fetchall()
    pending = conn.execute('''
      SELECT COUNT(*) FROM tickets
      WHERE COALESCE(fecha_solicitud,fecha_creacion)<?
      AND (COALESCE(fecha_resolucion,fecha_cierre) IS NULL OR COALESCE(fecha_resolucion,fecha_cierre)>=?)
      AND estado NOT IN ('Cancelado')
    ''', (end, end)).fetchone()[0]
    hours = sum(row['horas_efectivas'] or 0 for row in resolved)
    value = sum((row['valor_estimado'] or 0) if (row['valor_estimado'] or 0)>0 else (row['horas_efectivas'] or 0)*36700 for row in resolved)
    first_measured = [r for r in received if r['fecha_primera_atencion'] and r['sla_primera_minutos']]
    resolution_measured = [r for r in received if r['fecha_resolucion'] and r['sla_resolucion_minutos']]

    def compliance(rows, date_field, limit_field):
        if not rows: return None
        ok=0
        for r in rows:
            base=datetime.fromisoformat(r['fecha_solicitud'] or r['fecha_creacion'])
            done=datetime.fromisoformat(r[date_field])
            ok += (done-base).total_seconds() <= r[limit_field]*60
        return round(ok*100/len(rows))

    sla_first=compliance(first_measured,'fecha_primera_atencion','sla_primera_minutos')
    sla_resolution=compliance(resolution_measured,'fecha_resolucion','sla_resolucion_minutos')

    with csv_path.open('w', newline='', encoding='utf-8-sig') as fh:
        writer=csv.writer(fh, delimiter=';')
        writer.writerow(['Número','Cliente','Asunto','Categoría','Prioridad','Modalidad','Técnico','Horas','Valor estimado','Fecha resolución'])
        for r in resolved:
            item_value=(r['valor_estimado'] or 0) if (r['valor_estimado'] or 0)>0 else (r['horas_efectivas'] or 0)*36700
            writer.writerow([r['numero'],r['cliente'],r['asunto'],r['categoria'],r['prioridad'],r['modalidad'],r['tecnico'],r['horas_efectivas'] or 0,round(item_value),r['fecha_resolucion'] or r['fecha_cierre']])

    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallCell',parent=styles['BodyText'],fontSize=6.5,leading=8,textColor=colors.HexColor('#243145')))
    styles.add(ParagraphStyle(name='TitleOT',parent=styles['Title'],fontSize=20,leading=24,textColor=colors.HexColor('#14213D')))
    doc=SimpleDocTemplate(str(pdf_path),pagesize=landscape(A4),leftMargin=15*mm,rightMargin=15*mm,topMargin=20*mm,bottomMargin=15*mm,title=f'Informe de Gestión {start:%d/%m/%Y} - {end:%d/%m/%Y}',author='TicketFlow contributors')
    story=[Paragraph('Informe automático de Gestión TI',styles['TitleOT']),Paragraph(f'Período: {start:%d/%m/%Y} (inclusive) al {end:%d/%m/%Y} (exclusivo)',styles['Heading2']),Spacer(1,4*mm)]
    summary=[['Recibidos','Resueltos','Pendientes al corte','Horas efectivas','Valor estimado','SLA atención','SLA resolución'],[len(received),len(resolved),pending,f'{hours:.2f}',f'${value:,.0f}'.replace(',','.'),f'{sla_first}%' if sla_first is not None else '-',f'{sla_resolution}%' if sla_resolution is not None else '-']]
    st=Table(summary,colWidths=[35*mm]*7)
    st.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#14213D')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('BACKGROUND',(0,1),(-1,1),colors.HexColor('#EDF3F8')),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#CCD6E2')),('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story += [st,Spacer(1,7*mm),Paragraph('Tickets resueltos en el período',styles['Heading2'])]
    rows=[[Paragraph(x,styles['SmallCell']) for x in ['Ticket','Cliente','Asunto','Categoría','Prioridad','Horas','Valor']]]
    for r in resolved:
        item_value=(r['valor_estimado'] or 0) if (r['valor_estimado'] or 0)>0 else (r['horas_efectivas'] or 0)*36700
        rows.append([Paragraph(str(x or '-'),styles['SmallCell']) for x in [r['numero'],r['cliente'],r['asunto'],r['categoria'],r['prioridad'],f"{r['horas_efectivas'] or 0:.2f}",f'${item_value:,.0f}'.replace(',','.')]])
    table=Table(rows,colWidths=[23*mm,36*mm,88*mm,48*mm,25*mm,20*mm,29*mm],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#2457A6')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#D8DEE7')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F7F9FC')]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story.append(table)
    doc.build(story,onFirstPage=header_footer,onLaterPages=header_footer)
    conn.close()
    print(pdf_path)
    print(csv_path)


if __name__ == '__main__':
    main()
