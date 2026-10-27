"""Pedidos, menú diario y estados persistentes en Google Sheets."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from numbers import Integral
from threading import RLock
from uuid import uuid4, UUID
import pandas as pd
import streamlit as st
from zoneinfo import ZoneInfo
from access import require_role
from cloudstore import tab, workbook

ORDER_HEADERS = ['pedido', 'linea', 'fecha', 'hora', 'mesa', 'plato', 'cantidad',
                 'precio', 'total', 'trabajador', 'estado', 'tipo', 'pago']
STATE_HEADERS = ['pedido', 'fecha', 'estado', 'cocinero']
MENU_HEADERS = ['id', 'dia', 'nombre', 'precio', 'activo', 'administrador', 'actualizado']
# Community Cloud ejecuta las sesiones en un proceso. Evita doble envío en ese proceso.
WRITE_LOCK = RLock()


def now():
    return datetime.now(ZoneInfo('America/Lima'))


def amount(value):
    try:
        result = Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError('Precio inválido.') from None
    if not result.is_finite() or result <= 0 or result > 10000:
        raise ValueError('El precio debe estar entre S/ 0.01 y S/ 10,000.')
    return result


def _menu(day):
    latest = {}
    for row in tab('AppMenuDia', MENU_HEADERS).get_all_values()[1:]:
        if len(row) >= 5 and row[1] == day:
            latest[row[0]] = row
    return [{'clave': row[0], 'nombre': row[2], 'precio': float(amount(row[3])), 'tipo': 'Menú'}
            for row in latest.values() if row[4].lower() == 'true']


def daily_menu(day=None):
    require_role('usuario', 'trabajador')
    day = day or now().date()
    if not isinstance(day, date):
        raise ValueError('Fecha inválida.')
    return _menu(day.isoformat())


def save_menu(name, price, day, item_id=None, active=True):
    actor = require_role('usuario')
    name = name.strip()
    if not name or len(name) > 100 or not isinstance(day, date):
        raise ValueError('Introduce un nombre de hasta 100 caracteres y una fecha válida.')
    price = amount(price)
    with WRITE_LOCK:
        current = _menu(day.isoformat())
        if item_id and not any(item['clave'] == item_id for item in current):
            raise ValueError('Ese plato ya no está disponible. Actualiza la lista.')
        if active and any(item['nombre'].casefold() == name.casefold() and item['clave'] != item_id for item in current):
            raise ValueError('Ya existe un plato con ese nombre para este día.')
        tab('AppMenuDia', MENU_HEADERS).append_row([
            item_id or str(uuid4()), day.isoformat(), name, float(price),
            'true' if active else 'false', actor, now().isoformat(),
        ], value_input_option='RAW')


def catalog(kind):
    require_role('usuario', 'trabajador')
    if kind == 'Menú':
        return _menu(now().date().isoformat())
    if kind != 'Plato a la carta':
        raise ValueError('Tipo de plato inválido.')
    rows = workbook().worksheet('Carta').get('A1:C1000', value_render_option='UNFORMATTED_VALUE')
    header = next((i for i, row in enumerate(rows) if len(row) >= 3 and row[0] == 'Producto'), None)
    if header is None:
        raise ValueError('No se encontró la cabecera de Carta.')
    result = []
    names = set()
    for raw in rows[header + 1:]:
        row = list(raw) + ['', '', '']
        if not str(row[0]).strip() or row[2] == '' or row[1] == 'Menús y porciones':
            continue
        name = str(row[0]).strip()
        if name in names:
            raise ValueError('La carta contiene nombres duplicados.')
        names.add(name)
        result.append({'clave': name, 'nombre': name, 'precio': float(amount(row[2])), 'tipo': kind})
    return result


def _all_orders():
    rows = tab('AppPedidos', ORDER_HEADERS).get_all_values()[1:]
    data = pd.DataFrame([row + [''] * (len(ORDER_HEADERS) - len(row)) for row in rows if row and row[0]], columns=ORDER_HEADERS)
    for col in ('cantidad', 'precio', 'total'):
        data[col] = pd.to_numeric(data[col], errors='raise')
    states = {}
    for row in tab('AppPedidoEstados', STATE_HEADERS).get_all_values()[1:]:
        if len(row) >= 3 and row[2] == 'listo':
            states[row[0]] = 'listo'
    data['estado'] = [states.get(row.pedido, 'pendiente') for row in data.itertuples()]
    return data


def orders():
    require_role('usuario', 'cocinero')
    return _all_orders()


def submit_order(table, items, payment, request_id, quoted_total):
    worker = require_role('usuario', 'trabajador')
    if not isinstance(table, Integral) or not 1 <= table <= 999:
        raise ValueError('La mesa debe ser un número entre 1 y 999.')
    if payment not in ('Efectivo', 'Yape', 'Plin', 'Tarjeta', 'Otro'):
        raise ValueError('Medio de pago inválido.')
    try:
        request_id = str(UUID(str(request_id)))
    except ValueError:
        raise ValueError('Identificador del pedido inválido.') from None
    if not items or len(items) > 30:
        raise ValueError('Añade entre 1 y 30 platos al pedido.')
    with WRITE_LOCK:
        existing = _all_orders()
        previous = existing[existing.pedido == request_id]
        if not previous.empty:
            if set(previous.trabajador) != {worker}:
                raise PermissionError('Este pedido pertenece a otro usuario.')
            return request_id
        catalogs = {kind: {p['clave']: p for p in catalog(kind)} for kind in {i['tipo'] for i in items}}
        timestamp = now()
        rows, seen = [], set()
        for item in items:
            kind, key, qty = item['tipo'], item['clave'], item['cantidad']
            if not isinstance(qty, Integral) or not 1 <= qty <= 100:
                raise ValueError('Cada cantidad debe ser un entero entre 1 y 100.')
            if (kind, key) in seen:
                raise ValueError('Un plato está repetido. Combina sus cantidades.')
            seen.add((kind, key))
            product = catalogs[kind].get(key)
            if not product:
                raise ValueError('Un plato dejó de estar disponible. Actualiza tu selección.')
            price = amount(product['precio'])
            rows.append([request_id, str(uuid4()), timestamp.date().isoformat(),
                         timestamp.strftime('%H:%M:%S'), int(table), product['nombre'], int(qty),
                         float(price), float(price * qty), worker, 'pendiente', kind, payment])
        total = sum((Decimal(str(row[8])) for row in rows), Decimal('0'))
        if total != Decimal(str(quoted_total)).quantize(Decimal('.01')):
            raise ValueError('Cambió un precio. Actualiza el pedido antes de enviarlo.')
        # Un único append para todas las líneas; precios e identidad se resuelven en servidor.
        tab('AppPedidos', ORDER_HEADERS).append_rows(rows, value_input_option='RAW')
        return request_id


def mark_ready(order_ids):
    cook = require_role('usuario', 'cocinero')
    with WRITE_LOCK:
        data = _all_orders()
        pending = set(data.loc[data.estado == 'pendiente', 'pedido'])
        targets = set(order_ids)
        if targets - set(data.pedido):
            raise ValueError('Un pedido ya no existe. Actualiza la cocina.')
        rows = [[key, now().isoformat(), 'listo', cook] for key in sorted(targets & pending)]
        if rows:
            tab('AppPedidoEstados', STATE_HEADERS).append_rows(rows, value_input_option='RAW')


def report_sales():
    require_role('usuario')
    data = _all_orders()
    data['id'] = data.linea
    data['id_pedido'] = data.pedido
    data['producto'] = data.plato
    data['referencia'] = data.mesa.astype(str)
    data['canal'] = 'Salón'
    data['fecha'] = data.fecha.astype(str) + 'T' + data.hora.astype(str) + '-05:00'
    return data
