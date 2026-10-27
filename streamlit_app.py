"""Cloud entrypoint: require durable storage before accepting sales."""
from pathlib import Path
import runpy
import streamlit as st
try:
    ready=bool(st.secrets.get('gcp_service_account'))
except FileNotFoundError:
    ready=False
if not ready:
    st.set_page_config(page_title='Cocina de Siempre',page_icon='🍲')
    st.title('Cocina de Siempre')
    st.info('Falta conectar el guardado permanente en Google Sheets. El propietario debe añadir gcp_service_account en Settings → Secrets y compartir la hoja con la cuenta de servicio como editor.')
    st.stop()
runpy.run_path(str(Path(__file__).with_name('app.py')),run_name='__main__')
