"""Administrador con Google; personal con credenciales individuales y hash scrypt."""
import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4
import streamlit as st

OWNER = 'centenobustos97@gmail.com'
STAFF_HEADERS = ['usuario', 'hash', 'rol', 'activo', 'version', 'fecha', 'administrador']
ATTEMPT_HEADERS = ['usuario', 'fecha', 'resultado']
SESSION_SECONDS = 8 * 60 * 60
LOGIN_LOCK = threading.RLock()


def _google_owner():
    return (bool(st.user.get('is_logged_in', False))
            and st.user.get('iss') in ('https://accounts.google.com', 'accounts.google.com')
            and st.user.get('email_verified') is True
            and str(st.user.get('email', '')).strip().lower() == OWNER)


@st.cache_data(ttl=5, show_spinner=False)
def _accounts():
    from cloudstore import tab
    latest = {}
    for row in tab('AppPersonal', STAFF_HEADERS).get_all_values()[1:]:
        if len(row) == len(STAFF_HEADERS):
            latest[row[0]] = row
    return latest


def _staff_session():
    session = st.session_state.get('_staff_auth')
    if not isinstance(session, dict) or session.get('expires', 0) <= time.time():
        st.session_state.pop('_staff_auth', None)
        raise PermissionError('Inicia sesión con tu usuario y contraseña.')
    row = _accounts().get(session.get('username'))
    if (not row or row[3] != 'true' or row[4] != session.get('version')
            or row[2] not in ('trabajador', 'cocinero')):
        st.session_state.pop('_staff_auth', None)
        raise PermissionError('Tu acceso cambió. Vuelve a iniciar sesión.')
    return row


def _principal():
    if _google_owner():
        return OWNER, 'usuario'
    account = _staff_session()
    return account[0], account[2]


def email():
    return _principal()[0]


def role():
    return _principal()[1]


def require_role(*allowed):
    actor, current = _principal()
    if current not in allowed:
        raise PermissionError('Tu rol no permite esta operación.')
    return actor


def _password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt),
                            n=16384, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)
    return 'scrypt$' + salt + '$' + digest.hex()


def _password_matches(password, encoded):
    try:
        algorithm, salt, _ = encoded.split('$')
        if algorithm != 'scrypt':
            return False
        return hmac.compare_digest(_password_hash(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def _username(value):
    username = value.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}', username):
        raise ValueError('El usuario debe tener entre 3 y 40 letras, números, puntos, guiones o guiones bajos.')
    return username


def _clear_personal_state():
    for key in list(st.session_state):
        if key == '_staff_auth' or key == 'show_sale' or key == 'mainnav' or key.startswith(('sale_', 'cart_')):
            del st.session_state[key]


def login_staff(username, password):
    from cloudstore import tab
    username = _username(username)
    if not isinstance(password, str) or len(password) > 128:
        raise PermissionError('Usuario o contraseña incorrectos.')
    with LOGIN_LOCK:
        attempts = tab('AppPersonalIntentos', ATTEMPT_HEADERS)
        now = time.time()
        failed = 0
        for row in attempts.get_all_values()[1:]:
            if len(row) != 3 or row[0] != username:
                continue
            try:
                recent = float(row[1]) > now - 900
            except ValueError:
                continue
            if recent:
                failed = failed + 1 if row[2] == 'fallo' else 0
        if failed >= 5:
            raise PermissionError('Demasiados intentos. Espera 15 minutos y vuelve a intentarlo.')
        account = _accounts().get(username)
        encoded = account[1] if account else 'scrypt$' + '00' * 16 + '$' + '00' * 32
        matches = _password_matches(password, encoded)
        valid = bool(account and account[3] == 'true' and account[2] in ('trabajador', 'cocinero') and matches)
        attempts.append_row([username, str(now), 'correcto' if valid else 'fallo'], value_input_option='RAW')
        if not valid:
            raise PermissionError('Usuario o contraseña incorrectos.')
        # Borra datos de cualquier sesión anterior antes de identificar al trabajador.
        _clear_personal_state()
        st.session_state['_staff_auth'] = {
            'username': username, 'version': account[4], 'expires': now + SESSION_SECONDS,
        }
        return account[2]


def staff_accounts():
    require_role('usuario')
    return [{'Usuario': row[0], 'Rol': row[2], 'Activo': row[3] == 'true'}
            for row in _accounts().values()]


def save_staff(username, assigned_role, password=None, active=True, create=False):
    actor = require_role('usuario')
    username = _username(username)
    if assigned_role not in ('trabajador', 'cocinero'):
        raise ValueError('Rol no válido.')
    with LOGIN_LOCK:
        current = _accounts().get(username)
        if create and current:
            raise ValueError('Ese usuario ya existe. Usa su panel para modificarlo.')
        if not create and not current:
            raise ValueError('Ese usuario no existe.')
        if password is not None:
            if not isinstance(password, str) or not 12 <= len(password) <= 128:
                raise ValueError('La contraseña debe tener entre 12 y 128 caracteres.')
            encoded = _password_hash(password)
        elif current:
            encoded = current[1]
        else:
            raise ValueError('Introduce una contraseña para crear al usuario.')
        from cloudstore import tab
        tab('AppPersonal', STAFF_HEADERS).append_row([
            username, encoded, assigned_role, 'true' if active else 'false', str(uuid4()),
            datetime.now(timezone.utc).isoformat(), actor,
        ], value_input_option='RAW')
        _accounts.clear()
        # Un cambio de contraseña del dueño permite entrar sin conservar un bloqueo previo.
        if password is not None:
            tab('AppPersonalIntentos', ATTEMPT_HEADERS).append_row(
                [username, str(time.time()), 'restablecido'], value_input_option='RAW')


def _logout():
    _clear_personal_state()
    if st.user.get('is_logged_in', False):
        st.logout()
    else:
        st.rerun()


def require_user():
    try:
        current = role()
    except PermissionError:
        current = None
    except Exception:
        st.error('No se pudo comprobar el acceso. Vuelve a intentarlo.')
        st.stop()
    if current is None:
        st.title('La cocina de siempre')
        st.caption('Trabajadores y cocineros')
        with st.form('staff_login', clear_on_submit=True):
            username = st.text_input('Usuario', max_chars=40)
            password = st.text_input('Contraseña', type='password', max_chars=128)
            submitted = st.form_submit_button('Entrar', type='primary', width='stretch')
        if submitted:
            try:
                login_staff(username, password)
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))
            except Exception:
                st.error('No se pudo iniciar sesión. Vuelve a intentarlo.')
            else:
                st.rerun()
        st.divider()
        st.caption('Administrador · ' + OWNER)
        if st.user.get('is_logged_in', False) and not _google_owner():
            if st.button('Cambiar a la cuenta de administrador'):
                _logout()
        else:
            try:
                configured = bool(st.secrets.get('auth', {}).get('client_id'))
            except FileNotFoundError:
                configured = False
            if configured and st.button('Administrador: entrar con Google'):
                _clear_personal_state()
                st.login()
        st.stop()
    with st.sidebar:
        st.caption(email())
        st.caption({'usuario': 'Usuario · Administrador', 'trabajador': 'Trabajador', 'cocinero': 'Cocinero'}[current])
        if st.button('Cerrar sesión'):
            _logout()
    return current
