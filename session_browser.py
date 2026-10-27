"""Sesiones opacas en Sheets; el navegador solo conserva un token aleatorio."""
import hashlib
import re
import secrets
import time
from uuid import uuid4
import streamlit as st

HEADERS = ['sesion_hash', 'usuario', 'version', 'vence', 'activa']
COOKIE_NAME = '__Host-cocina_staff'

@st.cache_data(ttl=5, show_spinner=False)
def _records():
    from cloudstore import tab
    latest = {}
    for row in tab('AppSesiones', HEADERS).get_all_values()[1:]:
        if len(row) == len(HEADERS):
            latest[row[0]] = row
    return latest

def _digest(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()

def create(username, version, expires):
    from cloudstore import tab
    token = secrets.token_urlsafe(32)
    tab('AppSesiones', HEADERS).append_row(
        [_digest(token), username, version, str(expires), 'true'], value_input_option='RAW')
    _records.clear()
    return token

def restore(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    record = _records().get(_digest(token))
    if not record or record[4] != 'true':
        return None
    try:
        expires = float(record[3])
    except ValueError:
        return None
    if expires <= time.time():
        return None
    return {'username': record[1], 'version': record[2], 'expires': expires, 'token': token}

def revoke(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return
    from cloudstore import tab
    record = _records().get(_digest(token))
    if record:
        tab('AppSesiones', HEADERS).append_row(record[:4] + ['false'], value_input_option='RAW')
        _records.clear()

def queue_cookie(token='', expires=0):
    st.session_state['_cookie_command'] = {
        'id': str(uuid4()), 'action': 'set' if token else 'delete',
        'token': token, 'expires': expires,
    }

# Componente mínimo: no guarda contraseñas ni incorpora código de usuarios.
_BRIDGE = st.components.v2.component('remember_staff_session',
    html='<span id="session-bridge" aria-hidden="true"></span>',
    js=r'''export default function({data, parentElement, setStateValue}) {
      const marker = parentElement.querySelector('#session-bridge');
      const name = '__Host-cocina_staff';
      const read = () => {
        const row = document.cookie.split('; ').find(p => p.startsWith(name + '='));
        return row ? decodeURIComponent(row.slice(name.length + 1)) : '';
      };
      let available = true;
      let token = '';
      const command = data?.command;
      try {
        if (command?.action === 'set') {
          const age = Math.max(0, Math.floor(command.expires - Date.now() / 1000));
          document.cookie = name + '=' + encodeURIComponent(command.token)
            + '; Path=/; Max-Age=' + age + '; Secure; SameSite=Lax';
        } else if (command?.action === 'delete') {
          document.cookie = name + '=; Path=/; Max-Age=0; Secure; SameSite=Lax';
        }
        token = read();
        if (command?.action === 'set' && token !== command.token) available = false;
        if (command?.action === 'delete' && token) available = false;
      } catch (_) { available = false; }
      const result = {ready:true, token, available, ack:command?.id || ''};
      const signature = JSON.stringify(result);
      if (marker.dataset.signature !== signature) {
        marker.dataset.signature = signature;
        setStateValue('result', result);
      }
    }''')

def browser_state():
    command = st.session_state.get('_cookie_command')
    result = _BRIDGE(key='staff_cookie_bridge', data={'command': command},
        default={'result': None}, on_result_change=lambda: None, height=0)
    state = result.result
    if not state or not state.get('ready') or (command and state.get('ack') != command['id']):
        st.caption('Recuperando tu sesión…')
        st.stop()
    if command:
        st.session_state.pop('_cookie_command', None)
    if not state.get('available', False):
        st.warning('El navegador bloqueó la cookie de sesión. Permite las cookies de esta página para conservar el acceso al recargar.')
    return state.get('token', '')
