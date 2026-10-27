from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from storage import sales, add_sale, advance, cloud_enabled
ROOT = Path(__file__).parent
CARTA_PATH = ROOT/'data'/'carta.csv' if (ROOT/'data'/'carta.csv').exists() else ROOT/'carta.csv'
SHEET_ID = '13PbD43VxDNgPo1dsG3FwsKmUlU7SGUfiBj1cC9oXiL0'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit'
st.set_page_config(page_title='Cocina de Siempre', page_icon='🍲', layout='wide')
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
    page = st.radio('Mi restaurante', ['Resumen','Datos de venta','Ventas','Cocina','Carta'])
    st.divider()
    st.link_button('Abrir hoja de precios ↗', SHEET_URL)
    if st.button('Actualizar precios de Sheets'):
        try:
            refresh_prices()
            st.success('Precios actualizados desde Carta.')
        except Exception:
            st.warning('No se pudo leer Carta. Se conserva la copia local. Para una hoja privada configura credenciales según LEEME.md.')
    st.caption('Precios: copia de Carta o última actualización manual.')
    st.caption('Ventas compartidas en Google Sheets' if cloud_enabled() else 'Ventas guardadas en este equipo')
carta = pd.read_csv(CARTA_PATH)
st.caption('MI RESTAURANTE / LOCAL PRINCIPAL')
heading, action = st.columns([4,1])
with heading:
    st.title({'Resumen':'Cocina de Siempre.','Datos de venta':'Tu día, en un vistazo.','Ventas':'Cada venta cuenta.','Cocina':'El corazón de tu cocina.','Carta':'Los sabores de siempre.'}[page])
    st.caption('Cada plato cuenta. Cada decisión también.')
def new_sale():
    available = carta.dropna(subset=['Precio'])
    if available.empty:
        st.warning('No hay productos con precio definido.')
        return
    product = st.selectbox('Producto', available.Producto.tolist())
    price = float(available.loc[available.Producto==product,'Precio'].iloc[0])
    st.info(f'Precio unitario: {money(price)}')
    with st.form('venta'):
        quantity = st.number_input('Cantidad', min_value=1,max_value=100,value=1,step=1)
        channel = st.selectbox('Canal', ['Salón','Delivery','Para llevar'])
        reference = st.text_input('Mesa o referencia',max_chars=100)
        payment = st.selectbox('Pago', ['Efectivo','Yape','Plin','Tarjeta','Otro'])
        if st.form_submit_button('Registrar venta',type='primary'):
            add_sale(product,quantity,price,channel,reference,payment)
            st.session_state['show_sale'] = False
            st.rerun()
    st.caption('Las bebidas sin precio se muestran en Carta; todavía no se pueden vender.')
with action:
    if st.button('＋ Nueva venta',type='primary'):
        st.session_state['show_sale'] = True
if st.session_state.get('show_sale'):
    with st.expander('Registrar venta', expanded=True):
        new_sale()
if page=='Resumen':
    st.info('Consulta los filtros, indicadores, gráficos y últimas ventas en Datos de venta, en el menú izquierdo.')
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
    if page=='Cocina':
        pending = data[data.estado!='Entregado']
        if pending.empty:
            st.success('Todo al día. No hay pedidos pendientes con estos filtros.')
        for _,order in pending.iterrows():
            with st.container(border=True):
                st.subheader(f'{order.cantidad} × {order.producto}')
                st.write(f'{order.canal} · {order.referencia or "Sin referencia"} · {order.estado}')
                if st.button('Iniciar preparación' if order.estado=='Pendiente' else 'Marcar entregado',key=order.id):
                    advance(order.id)
                    st.rerun()
    else:
        if page=='Datos de venta':
            total = data.total.sum()
            for col,label,value in zip(st.columns(4),['Ventas totales','Ventas registradas','Ticket promedio','Productos vendidos'],[money(total),len(data),money(total/len(data) if len(data) else 0),int(data.cantidad.sum())]):
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




