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
MENU_HEADERS = ['id', 'dia', 'nombre', 'precio', 'activo', 'administrador', 'actualizado', 'categoria']
MENU_CATEGORIES = ('Caldo / sopa', 'Entrada', 'Segundo')
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


def menu_category(name):
    import unicodedata
    normalized = ''.join(c for c in unicodedata.normalize('NFKD', name.casefold()) if not unicodedata.combining(c))
    if 'caldo' in normalized or 'sopa' in normalized:
        return 'Caldo / sopa'
    if any(word in normalized for word in ('entrada', 'ensalada', 'huancaina', 'causa')):
        return 'Entrada'
    return 'Segundo'


def menu_price(value, category):
    if category != 'Segundo' and str(value).strip() in ('0', '0.0', '0.00'):
        return Decimal('0')
    return amount(value)


def combo_name(product, accompaniment_ids, available):
    if not isinstance(accompaniment_ids, list) or len(accompaniment_ids) > 2:
        raise ValueError('Elige como máximo un caldo/sopa y una entrada por menú.')
    labels, used = [], set()
    for key in accompaniment_ids:
        item = available.get(key)
        if not item or item['categoria'] not in ('Caldo / sopa', 'Entrada'):
            raise ValueError('Un acompañamiento cambió. Vuelve a seleccionar el menú.')
        category = item['categoria']
        if category in used:
            raise ValueError('Elige solo un plato por tipo de acompañamiento.')
        used.add(category)
        labels.append(f"{category}: {item['nombre']}")
    return product['nombre'] + (' · ' + ' · '.join(labels) if labels else '')


def _menu(day):
    latest = {}
    for row in tab('AppMenuDia', MENU_HEADERS).get_all_values()[1:]:
        if len(row) >= 5 and row[1] == day:
            latest[row[0]] = row
    result = []
    for row in latest.values():
        if row[4].lower() != 'true':
            continue
        category = row[7] if len(row) > 7 and row[7] in MENU_CATEGORIES else menu_category(row[2])
        result.append({'clave': row[0], 'nombre': row[2], 'precio': float(menu_price(row[3], category)),
                       'tipo': 'Menú', 'categoria': category})
    return result


def daily_menu(day=None):
    require_role('usuario', 'trabajador')
    day = day or now().date()
    if not isinstance(day, date):
        raise ValueError('Fecha inválida.')
    return _menu(day.isoformat())


def save_menu(name, price, day, item_id=None, active=True, category=None):
    actor = require_role('usuario')
    name = name.strip()
    if not name or len(name) > 100 or not isinstance(day, date):
        raise ValueError('Introduce un nombre de hasta 100 caracteres y una fecha válida.')
    with WRITE_LOCK:
        current = _menu(day.isoformat())
        if item_id and not any(item['clave'] == item_id for item in current):
            raise ValueError('Ese plato ya no está disponible. Actualiza la lista.')
        if active and any(item['nombre'].casefold() == name.casefold() and item['clave'] != item_id for item in current):
            raise ValueError('Ya existe un plato con ese nombre para este día.')
        previous = next((item for item in current if item['clave'] == item_id), None)
        category = category or (previous['categoria'] if previous else menu_category(name))
        if category not in MENU_CATEGORIES:
            raise ValueError('Selecciona Caldo / sopa, Entrada o Segundo.')
        price = menu_price(price, category)
        tab('AppMenuDia', MENU_HEADERS).append_row([
            item_id or str(uuid4()), day.isoformat(), name, float(price),
            'true' if active else 'false', actor, now().isoformat(), category,
        ], value_input_option='RAW')


def catalog(kind):
    require_role('usuario', 'trabajador')
    if kind in ('Menú', 'Menú completo'):
        menu = _menu(now().date().isoformat())
        return [item for item in menu if item['categoria'] == 'Segundo'] if kind == 'Menú completo' else menu
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


@st.cache_data(ttl=5, show_spinner=False)
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
        _all_orders.clear()
        existing = _all_orders()
        previous = existing[existing.pedido == request_id]
        if not previous.empty:
            if set(previous.trabajador) != {worker}:
                raise PermissionError('Este pedido pertenece a otro usuario.')
            return request_id
        catalogs = {kind: {p['clave']: p for p in catalog('Menú' if kind == 'Menú completo' else kind)} for kind in {i['tipo'] for i in items}}
        timestamp = now()
        rows, seen = [], set()
        for item in items:
            kind, key, qty = item['tipo'], item['clave'], item['cantidad']
            if not isinstance(qty, Integral) or not 1 <= qty <= 100:
                raise ValueError('Cada cantidad debe ser un entero entre 1 y 100.')
            accompanying = item.get('acompanamientos', [])
            if not isinstance(accompanying, list) or not all(isinstance(k, str) for k in accompanying) or len(accompanying) > 2:
                raise ValueError('Selección de acompañamientos no válida.')
            identity = (kind, key, tuple(sorted(accompanying)))
            if identity in seen:
                raise ValueError('Un plato está repetido. Combina sus cantidades.')
            seen.add(identity)
            product = catalogs[kind].get(key)
            if not product:
                raise ValueError('Un plato dejó de estar disponible. Actualiza tu selección.')
            name = product['nombre']
            if kind in ('Menú', 'Menú completo'):
                if product['categoria'] != 'Segundo':
                    raise ValueError('Elige un segundo: el caldo/sopa y la entrada van incluidos.')
                name = combo_name(product, accompanying, catalogs[kind])
            elif accompanying:
                raise ValueError('Los acompañamientos incluidos son para el menú completo.')
            price = amount(product['precio'])
            rows.append([request_id, str(uuid4()), timestamp.date().isoformat(),
                         timestamp.strftime('%H:%M:%S'), int(table), name, int(qty),
                         float(price), float(price * qty), worker, 'pendiente', kind, payment])
        total = sum((Decimal(str(row[8])) for row in rows), Decimal('0'))
        if total != Decimal(str(quoted_total)).quantize(Decimal('.01')):
            raise ValueError('Cambió un precio. Actualiza el pedido antes de enviarlo.')
        # Un único append para todas las líneas; precios e identidad se resuelven en servidor.
        tab('AppPedidos', ORDER_HEADERS).append_rows(rows, value_input_option='RAW')
        _all_orders.clear()
        return request_id


def mark_ready(order_ids):
    cook = require_role('usuario', 'cocinero')
    with WRITE_LOCK:
        _all_orders.clear()
        data = _all_orders()
        pending = set(data.loc[data.estado == 'pendiente', 'pedido'])
        targets = set(order_ids)
        if targets - set(data.pedido):
            raise ValueError('Un pedido ya no existe. Actualiza la cocina.')
        rows = [[key, now().isoformat(), 'listo', cook] for key in sorted(targets & pending)]
        if rows:
            tab('AppPedidoEstados', STATE_HEADERS).append_rows(rows, value_input_option='RAW')
            _all_orders.clear()


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
