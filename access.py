"""Identidad Google verificada y autorizaciones revisadas en cada operación."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4
import streamlit as st

OWNER = 'centenobustos97@gmail.com'
ROLE_HEADERS = ['id', 'correo', 'rol', 'activo', 'fecha', 'administrador']


def email():
    if not st.user.is_logged_in:
        raise PermissionError('Inicia sesión con Google.')
    if st.user.get('iss') not in ('https://accounts.google.com', 'accounts.google.com'):
        raise PermissionError('Proveedor de identidad no autorizado.')
    if st.user.get('email_verified') is not True:
        raise PermissionError('Tu correo de Google debe estar verificado.')
    value = str(st.user.get('email', '')).strip().lower()
    if not value:
        raise PermissionError('Google no devolvió un correo verificado.')
    return value


def _assignments():
    from cloudstore import tab
    rows = tab('AppAccesos', ROLE_HEADERS).get_all_values()[1:]
    latest = {}
    for row in rows:
        if len(row) >= 4:
            latest[row[1].strip().lower()] = row
    return latest


def role():
    address = email()
    if address == OWNER:
        return 'usuario'
    row = _assignments().get(address)
    if row and row[3].lower() == 'true' and row[2] in ('trabajador', 'cocinero'):
        return row[2]
    raise PermissionError('Acceso denegado. Tu correo no está autorizado.')


def require_role(*allowed):
    current = role()
    if current not in allowed:
        raise PermissionError('Tu rol no permite esta operación.')
    return email()


def require_user():
    if not st.user.is_logged_in:
        st.title('La cocina de siempre')
        st.caption('Inicia sesión para entrar a tu restaurante.')
        try:
            configured = bool(st.secrets.get('auth', {}).get('client_id'))
        except FileNotFoundError:
            configured = False
        if not configured:
            st.error('Falta configurar Google OAuth en Secrets: consulta auth.example.toml.')
        elif st.button('Entrar con Google', type='primary'):
            st.login()
        st.stop()
    try:
        current = role()
    except PermissionError as exc:
        st.error(str(exc))
        if st.button('Usar otra cuenta'):
            st.logout()
        st.stop()
    except Exception:
        st.error('No se pudo comprobar el acceso. Inténtalo nuevamente.')
        st.stop()
    with st.sidebar:
        st.caption(email())
        st.caption({'usuario': 'Usuario · Administrador', 'trabajador': 'Trabajador', 'cocinero': 'Cocinero'}[current])
        if st.button('Cerrar sesión'):
            st.logout()
    return current


def authorized_emails():
    require_role('usuario')
    return [{'Correo': address, 'Rol': row[2]} for address, row in _assignments().items()
            if address != OWNER and row[3].lower() == 'true']


def set_access(address, assigned_role, active=True):
    actor = require_role('usuario')
    address = address.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', address):
        raise ValueError('Introduce un correo válido.')
    if address == OWNER:
        raise ValueError('El acceso del propietario no se puede modificar.')
    if assigned_role not in ('trabajador', 'cocinero'):
        raise ValueError('Rol no válido.')
    from cloudstore import tab
    tab('AppAccesos', ROLE_HEADERS).append_row([
        str(uuid4()), address, assigned_role, 'true' if active else 'false',
        datetime.now(ZoneInfo('America/Lima')).isoformat(), actor,
    ], value_input_option='RAW')
