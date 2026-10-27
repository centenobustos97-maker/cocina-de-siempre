"""Pantallas por rol; todos los permisos también se comprueban en servidor."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
import pandas as pd
import streamlit as st
import orders
from access import require_role, staff_accounts, save_staff


def _error(exc):
    if isinstance(exc, (PermissionError, ValueError)):
        st.error(str(exc))
    else:
        import logging
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        logging.getLogger('cocina').warning('Sheets operation failed: type=%s status=%s', type(exc).__name__, status)
        if status == 429:
            st.warning('Google Sheets está recibiendo demasiadas consultas. Espera un minuto y vuelve a intentarlo.')
        elif status in (401, 403):
            st.error('Google Sheets rechazó el acceso. El administrador debe revisar las credenciales y el permiso de edición de la hoja.')
        else:
            st.error('No se pudo cargar Google Sheets. Inténtalo nuevamente en unos segundos.')


def _add_cart(selected):
    cart = list(st.session_state.get('sale_cart', []))
    for item in selected:
        current = next((p for p in cart if (p['tipo'], p['clave']) == (item['tipo'], item['clave'])), None)
        if current:
            current['cantidad'] = min(100, current['cantidad'] + int(item['cantidad']))
            current['precio'] = item['precio']
        else:
            cart.append(dict(item))
    st.session_state.sale_cart = cart
    st.session_state.cart_revision = st.session_state.get('cart_revision', 0) + 1


@st.dialog('Menú del día', width='large')
def menu_dialog():
    require_role('usuario', 'trabajador')
    try:
        menu = orders.catalog('Menú')
        by_key = {item['clave']: item for item in menu}
        left, right = st.columns(2, gap='large')
        with left:
            st.subheader('Lista de menú')
            if menu:
                st.dataframe(pd.DataFrame(menu)[['nombre', 'precio']], hide_index=True,
                    width='stretch', column_config={
                        'nombre': 'Plato del día',
                        'precio': st.column_config.NumberColumn('Precio', format='S/ %.2f'),
                    })
                selected = st.multiselect('Selecciona los platos', list(by_key),
                    format_func=lambda key: by_key[key]['nombre'], key='menu_selection')
            else:
                st.info('Todavía no hay platos cargados para hoy. El administrador puede agregarlos en Menú del día.')
                selected = []
        with right:
            st.subheader('Cantidad y mesa')
            table = st.number_input('Número de mesa', min_value=1, max_value=999,
                step=1, key='menu_table')
            choices = []
            total = Decimal('0')
            if selected:
                for key in selected:
                    item = by_key[key]
                    quantity = st.number_input(f"Cantidad · {item['nombre']}",
                        min_value=1, max_value=100, value=1, step=1, key=f'menu_qty_{key}')
                    choices.append(dict(item, cantidad=int(quantity)))
                    total += orders.amount(item['precio']) * int(quantity)
            else:
                st.number_input('Cantidad de platos', min_value=1, value=1, step=1,
                    disabled=True, key='menu_empty_quantity')
                st.caption('Selecciona uno o varios platos en la lista de la izquierda.')
            st.metric('Total del menú', f'S/ {total:.2f}')
            if st.button('Añadir al pedido', type='primary', width='stretch', disabled=not choices):
                st.session_state.sale_table = int(table)
                _add_cart(choices)
                st.rerun()
    except Exception as exc:
        _error(exc)


def render_sale():
    require_role('usuario', 'trabajador')
    st.header('Venta')
    if flash := st.session_state.pop('sale_sent', None):
        st.success(f'Pedido {flash[:8]} enviado a cocina.')
    a, b = st.columns(2)
    if a.button('Plato a la carta', width='stretch', type='primary'):
        st.session_state.sale_kind = 'carta'
    if b.button('Menú', width='stretch'):
        st.session_state.menu_table = int(st.session_state.get('sale_table', 1))
        menu_dialog()
    if st.session_state.get('sale_kind', 'carta') == 'carta':
        try:
            products = orders.catalog('Plato a la carta')
        except Exception as exc:
            _error(exc)
            return
        if products:
            by_key = {p['clave']: p for p in products}
            with st.form('choose_a_la_carte'):
                key = st.selectbox('Plato', list(by_key), format_func=lambda k: f"{by_key[k]['nombre']} · S/ {by_key[k]['precio']:.2f}")
                qty = st.number_input('Cantidad', min_value=1, max_value=100, value=1, step=1)
                if st.form_submit_button('Añadir al pedido'):
                    _add_cart([dict(by_key[key], cantidad=int(qty))])
                    st.rerun()
        else:
            st.info('No hay platos a la carta con precio disponible.')
    table = st.number_input('Número de mesa', min_value=1, max_value=999, value=1, step=1, key='sale_table')
    payment = st.selectbox('Pago', ['Efectivo', 'Yape', 'Plin', 'Tarjeta', 'Otro'], key='sale_payment')
    cart = st.session_state.get('sale_cart', [])
    if not cart:
        st.info('Añade platos de la carta o del menú del día.')
        return
    display = pd.DataFrame([{'Plato': p['nombre'], 'Tipo': p['tipo'], 'Cantidad': p['cantidad'], 'Precio': p['precio'], 'Quitar': False} for p in cart])
    edited = st.data_editor(display, hide_index=True, width='stretch',
        disabled=['Plato', 'Tipo', 'Precio'], key=f"cart_{st.session_state.get('cart_revision', 0)}",
        column_config={'Cantidad': st.column_config.NumberColumn(min_value=1, max_value=100, step=1, required=True),
                       'Precio': st.column_config.NumberColumn(format='S/ %.2f')})
    chosen = []
    total = Decimal('0')
    for i, row in edited.iterrows():
        if row.Quitar:
            continue
        if pd.isna(row.Cantidad) or float(row.Cantidad) != int(row.Cantidad):
            st.warning('Cada cantidad debe ser un número entero.')
            return
        quantity = int(row.Cantidad)
        chosen.append({'tipo': cart[i]['tipo'], 'clave': cart[i]['clave'], 'cantidad': quantity})
        total += orders.amount(cart[i]['precio']) * quantity
    st.metric('Total a cobrar', f'S/ {total:.2f}')
    st.session_state.setdefault('sale_request', str(uuid4()))
    if st.button('Enviar', type='primary', disabled=not chosen, width='stretch'):
        try:
            order_id = orders.submit_order(int(table), chosen, payment, st.session_state.sale_request, total)
        except Exception as exc:
            _error(exc)
        else:
            st.session_state.sale_cart = []
            st.session_state.sale_request = str(uuid4())
            st.session_state.cart_revision = st.session_state.get('cart_revision', 0) + 1
            st.session_state.sale_sent = order_id
            st.rerun()


@st.fragment(run_every='10s')
def render_kitchen():
    require_role('usuario', 'cocinero')
    st.header('Cocina')
    st.caption('Pedidos pendientes por mesa · actualización automática cada 10 segundos')
    try:
        data = orders.orders()
        pending = data[data.estado == 'pendiente']
        if pending.empty:
            st.success('No hay pedidos pendientes.')
            return
        for table, table_rows in pending.groupby('mesa', sort=True):
            with st.container(border=True):
                st.subheader(f'Mesa {table}')
                for order_id, group in table_rows.groupby('pedido', sort=False):
                    st.caption(f"Pedido {order_id[:8]} · {group.iloc[0].fecha} {group.iloc[0].hora} · {group.iloc[0].trabajador}")
                    for line in group.itertuples():
                        st.write(f'{int(line.cantidad)} × {line.plato}')
                    if st.button('Listo', key=f'ready_{order_id}'):
                        orders.mark_ready([order_id])
                        st.rerun(scope='fragment')
                if st.button('Listo toda la mesa', key=f'ready_table_{table}'):
                    orders.mark_ready(table_rows.pedido.unique().tolist())
                    st.rerun(scope='fragment')
    except Exception as exc:
        _error(exc)


def render_menu_admin():
    require_role('usuario')
    st.header('Menú del día')
    day = st.date_input('Día del menú', value=orders.now().date())
    try:
        menu = orders.daily_menu(day)
    except Exception as exc:
        _error(exc)
        return
    with st.form('new_menu_item', clear_on_submit=True):
        name = st.text_input('Nombre del plato', max_chars=100)
        price = st.number_input('Precio (S/)', min_value=0.01, max_value=10000.0, value=12.0, step=0.5)
        if st.form_submit_button('Agregar plato', type='primary'):
            try:
                orders.save_menu(name, price, day)
            except Exception as exc:
                _error(exc)
            else:
                st.rerun()
    for item in menu:
        with st.expander(f"{item['nombre']} · S/ {item['precio']:.2f}"):
            with st.form(f"edit_menu_{item['clave']}"):
                name = st.text_input('Nombre', value=item['nombre'], max_chars=100)
                price = st.number_input('Precio', min_value=0.01, max_value=10000.0, value=item['precio'], step=0.5)
                if st.form_submit_button('Guardar cambios'):
                    try:
                        orders.save_menu(name, price, day, item['clave'])
                    except Exception as exc:
                        _error(exc)
                    else:
                        st.rerun()
            if st.button('Eliminar plato', key=f"remove_menu_{item['clave']}"):
                try:
                    orders.save_menu(item['nombre'], item['precio'], day, item['clave'], active=False)
                except Exception as exc:
                    _error(exc)
                else:
                    st.rerun()


def render_staff():
    require_role('usuario')
    st.header('Trabajadores y cocineros')
    st.caption('Crea cuentas con usuario y contraseña. El administrador conserva su acceso con Google.')
    with st.form('create_staff', clear_on_submit=True):
        username = st.text_input('Usuario', max_chars=40, help='Ejemplo: mozo01 o cocina01')
        password = st.text_input('Contraseña inicial', type='password', max_chars=128, help='Mínimo 12 caracteres')
        assigned = st.selectbox('Rol', ['trabajador', 'cocinero'])
        if st.form_submit_button('Crear usuario', type='primary'):
            try:
                save_staff(username, assigned, password, create=True)
            except Exception as exc:
                _error(exc)
            else:
                st.success('Usuario creado. Entrega sus credenciales directamente a esa persona.')
                st.rerun()
    try:
        entries = staff_accounts()
    except Exception as exc:
        _error(exc)
        return
    if not entries:
        st.info('Crea las cuentas del personal aquí. Los correos anteriores no se convierten automáticamente en usuarios.')
    for entry in entries:
        username = entry['Usuario']
        label = f"{username} · {entry['Rol']} · {'Activo' if entry['Activo'] else 'Desactivado'}"
        with st.expander(label):
            with st.form(f'edit_staff_{username}', clear_on_submit=True):
                assigned = st.selectbox('Rol', ['trabajador', 'cocinero'], index=0 if entry['Rol']=='trabajador' else 1)
                active = st.selectbox('Estado de la cuenta', ['Activa', 'Desactivada'], index=0 if entry['Activo'] else 1) == 'Activa'
                password = st.text_input('Nueva contraseña (opcional)', type='password', max_chars=128, help='Deja vacío para conservar la actual. Mínimo 12 caracteres.')
                if st.form_submit_button('Guardar cambios'):
                    try:
                        save_staff(username, assigned, password or None, active=active)
                    except Exception as exc:
                        _error(exc)
                    else:
                        st.rerun()


def render_reports():
    require_role('usuario')
    from storage import sales
    st.header('Ventas')
    try:
        data = sales()
    except Exception as exc:
        _error(exc)
        return
    if data.empty:
        st.info('Todavía no hay ventas registradas.')
        return
    data['fecha'] = pd.to_datetime(data.fecha, utc=True).dt.tz_convert('America/Lima')
    days = st.date_input('Días', value=(orders.now().date(), orders.now().date()))
    if len(days) == 2:
        data = data[(data.fecha.dt.date >= days[0]) & (data.fecha.dt.date <= days[1])]
    for column, label in [('mesa', 'Mesa'), ('trabajador', 'Trabajador'), ('producto', 'Plato')]:
        values = sorted(data[column].fillna('').astype(str).unique().tolist())
        selected = st.multiselect(label, values)
        if selected:
            data = data[data[column].fillna('').astype(str).isin(selected)]
    st.metric('Ventas del filtro', f'S/ {data.total.sum():.2f}')
    st.dataframe(data[['fecha', 'id_pedido', 'mesa', 'producto', 'cantidad', 'precio', 'total', 'trabajador', 'estado']], hide_index=True, width='stretch')
    st.download_button('Exportar ventas', data.to_csv(index=False).encode('utf-8-sig'), 'ventas.csv', 'text/csv')

