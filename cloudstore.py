"""Persistent Google Sheets backend. Status changes are append-only events."""
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4
import pandas as pd
import gspread
import streamlit as st
SHEET_ID='13PbD43VxDNgPo1dsG3FwsKmUlU7SGUfiBj1cC9oXiL0'
COLUMNS=['id','fecha','producto','cantidad','precio','canal','referencia','pago','estado']
@st.cache_resource(ttl=300)
def workbook():
    client=gspread.service_account_from_dict(dict(st.secrets['gcp_service_account']))
    return client.open_by_key(SHEET_ID)
def tab(name, headers):
    book=workbook()
    try:
        sheet=book.worksheet(name)
    except gspread.WorksheetNotFound:
        try:
            sheet=book.add_worksheet(title=name,rows=1000,cols=len(headers))
        except gspread.exceptions.APIError:
            sheet=book.worksheet(name)
    # A single header row is safe to write identically from concurrent sessions.
    if not sheet.row_values(1):
        sheet.update([headers],range_name='A1',value_input_option='RAW')
    if sheet.row_values(1)!=headers:
        raise ValueError(f'La cabecera de {name} no coincide con el formato de la aplicación.')
    return sheet

def legacy_sales():
    from access import require_role
    require_role('usuario', 'cocinero')
    rows=tab('AppVentas',COLUMNS).get_all_values()
    data=pd.DataFrame([r+['']*(len(COLUMNS)-len(r)) for r in rows[1:] if r and r[0]],columns=COLUMNS)
    for col in ['cantidad','precio']:
        data[col]=pd.to_numeric(data[col],errors='raise')
    events=tab('AppEstados',['id','estado','fecha']).get_all_values()[1:]
    states={}
    for r in events:
        if len(r)>=2:
            states[r[0]]=r[1]
    data['estado']=[states.get(row.id,row.estado) for row in data.itertuples()]
    data['total']=data.cantidad*data.precio
    return data.sort_values('fecha',ascending=False)
def add_sale(product,quantity,price,channel,reference,payment):
    from access import require_role
    require_role('usuario')
    tab('AppVentas',COLUMNS).append_row([str(uuid4()),datetime.now(ZoneInfo('America/Lima')).isoformat(),product,int(quantity),float(price),channel,reference,payment,'Pendiente'],value_input_option='RAW')
def advance(order_id):
    from access import require_role
    require_role('usuario', 'cocinero')
    data=legacy_sales()
    row=data[data.id==order_id]
    if row.empty or row.iloc[0].estado=='Entregado':
        return
    state='En preparación' if row.iloc[0].estado=='Pendiente' else 'Entregado'
    tab('AppEstados',['id','estado','fecha']).append_row([order_id,state,datetime.now(ZoneInfo('America/Lima')).isoformat()],value_input_option='RAW')


def sales():
    from access import require_role
    from orders import report_sales
    require_role('usuario')
    old = legacy_sales()
    old['trabajador'] = 'Histórico'
    old['mesa'] = old.referencia.fillna('').astype(str)
    old['id_pedido'] = old.id
    new = report_sales()
    columns = ['id', 'id_pedido', 'fecha', 'producto', 'cantidad', 'precio', 'canal',
               'referencia', 'pago', 'estado', 'total', 'trabajador', 'mesa']
    frames = [frame.reindex(columns=columns) for frame in (old, new) if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True).sort_values('fecha', ascending=False)
