import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4
import pandas as pd
DB = Path(__file__).parent / 'data' / 'ventas.sqlite3'
@contextmanager
def connection():
    con = sqlite3.connect(DB, timeout=20)
    con.execute('CREATE TABLE IF NOT EXISTS ventas (id TEXT PRIMARY KEY, fecha TEXT, producto TEXT, cantidad INTEGER, precio REAL, canal TEXT, referencia TEXT, pago TEXT, estado TEXT)')
    try:
        with con:
            yield con
    finally:
        con.close()
def sales():
    with connection() as con:
        return pd.read_sql_query('SELECT *, cantidad*precio AS total FROM ventas ORDER BY fecha DESC', con)
def add_sale(product, quantity, price, channel, reference, payment):
    with connection() as con:
        con.execute('INSERT INTO ventas VALUES (?,?,?,?,?,?,?,?,?)', (str(uuid4()), datetime.now(ZoneInfo('America/Lima')).isoformat(), product, int(quantity), float(price), channel, reference, payment, 'Pendiente'))
def advance(order_id):
    with connection() as con:
        con.execute("UPDATE ventas SET estado=CASE estado WHEN 'Pendiente' THEN 'En preparación' ELSE 'Entregado' END WHERE id=? AND estado!='Entregado'", (order_id,))


def cloud_enabled():
    import streamlit as st
    try:
        return bool(st.secrets.get('gcp_service_account'))
    except FileNotFoundError:
        return False

_local_sales, _local_add_sale, _local_advance = sales, add_sale, advance

def sales():
    from access import require_role
    require_role('usuario')
    if cloud_enabled():
        from cloudstore import sales as remote
        return remote()
    data = _local_sales()
    data['trabajador'] = 'Histórico'
    data['mesa'] = data.referencia.fillna('').astype(str)
    data['id_pedido'] = data.id
    return data

def add_sale(*args):
    from access import require_role
    require_role('usuario')
    if cloud_enabled():
        from cloudstore import add_sale as remote
        return remote(*args)
    return _local_add_sale(*args)

def advance(order_id):
    from access import require_role
    require_role('usuario', 'cocinero')
    if cloud_enabled():
        from cloudstore import advance as remote
        return remote(order_id)
    return _local_advance(order_id)
