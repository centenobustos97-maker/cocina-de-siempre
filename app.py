from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from storage import sales, cloud_enabled
from home import styles, render_home
from access import require_user
from role_views import render_sale, render_kitchen, render_menu_admin, render_staff, render_reports
ROOT = Path(__file__).parent
CARTA_PATH = ROOT/'data'/'carta.csv' if (ROOT/'data'/'carta.csv').exists() else ROOT/'carta.csv'
SHEET_ID = '13PbD43VxDNgPo1dsG3FwsKmUlU7SGUfiBj1cC9oXiL0'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit'
st.set_page_config(page_title='La cocina de siempre', page_icon='🍲', layout='wide')
styles()
with st.container(key='app-shell'):
    current_role = require_user()
    if current_role == 'trabajador':
        render_sale()
        st.stop()
    if current_role == 'cocinero':
        render_kitchen()
        st.stop()
    def money(value):
        return f'S/ {value:,.2f}'
    def refresh_prices():
        import csv, io, re
        from urllib.request import urlopen
        try:
            credentials = st.secrets.get('gcp_service_account')
        except FileNotFoundError:
            credentials = None
        if credentials:
            import gspread
            rows = gspread.service_account_from_dict(dict(credentials)).open_by_key(SHEET_ID).worksheet('Carta').get('A1:D1000')
        else:
            with urlopen(f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=1929133188', timeout=20) as response:
                rows = list(csv.reader(io.StringIO(response.read().decode('utf-8-sig'))))
        header = next((i for i,r in enumerate(rows) if len(r)>2 and r[0]=='Producto' and 'Precio' in str(r[2])), None)
        if header is None:
            raise ValueError('Cabecera de Carta no encontrada')
        products = []
        for row in rows[header+1:]:
            if not row or not row[0].strip():
                continue
            row = list(row)+['','','']
            price = None if not str(row[2]).strip() else float(re.sub(r'[^0-9.,-]', '', str(row[2])).replace(',',''))
            if price is not None and price <= 0:
                raise ValueError('Precio inválido')
            products.append({'Producto': row[0], 'Categoría': row[1], 'Precio': price})
        result = pd.DataFrame(products)
        if result.empty or result.Producto.duplicated().any():
            raise ValueError('Carta vacía o duplicada')
        temp = CARTA_PATH.with_suffix('.tmp')
        result.to_csv(temp,index=False)
        temp.replace(CARTA_PATH)
    with st.sidebar:
        st.title('Cocina de Siempre')
        st.caption('HECHO CON TRADICIÓN')
        page = st.radio('Mi restaurante', ['Inicio','Datos de venta','Ventas','Cocina','Carta','Menú del día','Personal'], key='mainnav')
        st.divider()
        st.link_button('Abrir hoja de precios ↗', SHEET_URL)
        if st.button('Actualizar precios de Sheets'):
            try:
                with st.spinner('Actualizando precios…'):
                    refresh_prices()
                    from orders import _display_catalog
                    _display_catalog.clear()
                st.success('Precios actualizados desde Carta.')
            except Exception:
                st.warning('No se pudo leer Carta. Se conserva la copia local. Para una hoja privada configura credenciales según LEEME.md.')
        st.caption('Precios: copia de Carta o última actualización manual.')
        st.caption('Ventas compartidas en Google Sheets' if cloud_enabled() else 'Ventas guardadas en este equipo')
    @st.cache_data(max_entries=2, show_spinner=False)
    def read_local_carta(path, modified):
        return pd.read_csv(path)

    carta = read_local_carta(str(CARTA_PATH), CARTA_PATH.stat().st_mtime_ns)
    if page != 'Inicio':
        st.caption('MI RESTAURANTE / LOCAL PRINCIPAL')
        heading, action = st.columns([4,1])
        with heading:
            st.title({'Datos de venta':'Tu día, en un vistazo.','Ventas':'Cada venta cuenta.',
                      'Cocina':'El corazón de tu cocina.','Carta':'Los sabores de siempre.',
                      'Menú del día':'Menú del día','Personal':'Personal'}[page])
        with action:
            if st.button('＋ Nueva venta', type='primary'):
                st.session_state['show_sale'] = True

    def new_sale():
        render_sale()

    if st.session_state.get('show_sale'):
        with st.expander('Registrar venta', expanded=True):
            new_sale()
    if page=='Inicio':
        render_home()
        if st.button('＋ Nueva venta', type='primary', key='home_sale'):
            st.session_state['show_sale'] = True
            st.rerun()
    elif page=='Menú del día':
        render_menu_admin()
    elif page=='Personal':
        render_staff()
    elif page=='Ventas':
        render_reports()
    elif page=='Cocina':
        render_kitchen()
    elif page=='Carta':
        category = st.selectbox('Categoría',['Todas']+carta['Categoría'].unique().tolist())
        view = carta if category=='Todas' else carta[carta['Categoría']==category]
        st.dataframe(view,hide_index=True,width='stretch',column_config={'Precio':st.column_config.NumberColumn('Precio (S/)',format='S/ %.2f')})
        st.info('Gaseosas, Chicha de Jora y Agua mineral: precio pendiente. Caldo (S/ 5) y Caldo de gallina (S/ 15) son productos distintos.')
    else:
        try:
            data = sales()
        except Exception:
            st.error('No se pudo acceder al registro de ventas. Comprueba las credenciales, los permisos de edición y la conexión con Google Sheets.')
            st.stop()
        a,b = st.columns(2)
        period = a.selectbox('Periodo',['Últimos 7 días','Hoy','Últimos 30 días','Todo'])
        channel = b.selectbox('Canal',['Todos','Salón','Delivery','Para llevar'])
        if not data.empty:
            data['fecha'] = pd.to_datetime(data.fecha,utc=True).dt.tz_convert('America/Lima')
            days = {'Últimos 7 días':7,'Hoy':1,'Últimos 30 días':30}.get(period)
            if days:
                start = datetime.now(ZoneInfo('America/Lima')).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=days-1)
                data = data[data.fecha>=start]
            if channel!='Todos':
                data = data[data.canal==channel]
        st.download_button('↓ Exportar CSV',data.drop(columns=['id']).to_csv(index=False).encode('utf-8-sig'),'cocina-ventas.csv','text/csv')
        if page=='Datos de venta':
            total = data.total.sum()
            for col,label,value in zip(st.columns(4),['Ventas totales','Ventas registradas','Ticket promedio','Productos vendidos'],[money(total),data.id_pedido.nunique(),money(total/data.id_pedido.nunique() if len(data) else 0),int(data.cantidad.sum())]):
                col.metric(label,value,border=True)
            left,right = st.columns([3,2])
            with left:
                st.subheader('Así van tus ventas')
                if not data.empty:
                    st.bar_chart(data.groupby(data.fecha.dt.date).total.sum(),color='#8fa77c',y_label='Ingresos (S/)')
                else:
                    st.info('Registra tu primera venta para ver el gráfico.')
            with right:
                st.subheader('Los favoritos de la casa')
                ranking = data.groupby('producto',as_index=False).agg(Unidades=('cantidad','sum'),Ingresos=('total','sum')).sort_values('Ingresos',ascending=False)
                st.dataframe(ranking.head(5),hide_index=True,width='stretch')
            st.subheader('Últimas ventas')
            data=data.head(5)
        else:
            st.subheader('Registro de ventas')
        st.dataframe(data.drop(columns=['id']),hide_index=True,width='stretch',column_config={'precio':st.column_config.NumberColumn('Precio unitario',format='S/ %.2f'),'total':st.column_config.NumberColumn('Total',format='S/ %.2f')})
    st.caption('Cada venta conserva su precio histórico. Sin conexión con caja ni SUNAT.')





