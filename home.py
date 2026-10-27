"""Portada visual y movimiento accesible, sin dependencias externas."""
from pathlib import Path
import base64
import streamlit as st
ROOT=Path(__file__).parent
@st.cache_data(show_spinner=False,max_entries=3)
def photo(name):
    return 'data:image/jpeg;base64,'+base64.b64encode((ROOT/name).read_bytes()).decode()

def styles():
    st.html('''<style>
    .st-key-mainnav [role="radiogroup"] {gap:8px;}
    .st-key-mainnav label {padding:10px 13px;border-radius:16px;transition:background .25s ease,transform .25s ease;}
    .st-key-mainnav label:hover {background:rgba(255,255,255,.09);transform:translateX(3px);}
    .st-key-mainnav label:has(input:checked) {background:rgba(255,255,255,.16);box-shadow:inset 0 0 0 1px rgba(255,255,255,.18);}
    .cs-hero {position:relative;isolation:isolate;overflow:hidden;border-radius:32px;min-height:510px;padding:44px;display:grid;grid-template-columns:1.1fr .9fr;gap:28px;align-items:center;background:#1b3728;color:#fff;box-shadow:0 20px 60px #19382820;animation:cs-arrive .75s cubic-bezier(.2,.8,.2,1) both;}
    .cs-hero-bg {position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center 56%;z-index:-3;animation:cs-settle 1.4s cubic-bezier(.2,.8,.2,1) both;}
    .cs-hero::before {content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(14,36,25,.94),rgba(20,42,28,.78) 50%,rgba(20,42,28,.25));z-index:-2;}
    .cs-home-eyebrow {font:600 11px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:.2em;color:#e0e9ca;margin:0 0 26px;}
    .cs-hero h1 {font:400 clamp(40px,4.7vw,70px)/1.04 Georgia,serif;letter-spacing:-.045em;color:white;margin:0 0 22px;max-width:540px;}
    .cs-hero h1 em {font-weight:400;color:#d6e5b5;}
    .cs-hero .cs-home-copy {font:400 16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:380px;color:#eef1e7;margin:0 0 30px;}
    .cs-glass-tag {display:inline-flex;align-items:center;gap:9px;padding:11px 15px;border-radius:100px;background:#ffffff18;border:1px solid #ffffff30;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);font:500 12px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
    .cs-dot {width:7px;height:7px;border-radius:50%;background:#d0e8a9;box-shadow:0 0 0 4px #d0e8a914;}
    .cs-photo-stack {height:370px;position:relative;}
    .cs-food-card {position:absolute;border:1px solid #ffffff55;border-radius:24px;overflow:hidden;box-shadow:0 18px 40px #00000030;animation:cs-arrive .9s .12s cubic-bezier(.2,.8,.2,1) both;}
    .cs-food-card img {display:block;width:100%;height:100%;object-fit:cover;}
    .cs-food-main {width:70%;height:315px;right:0;top:0;transform:rotate(5deg);}
    .cs-food-main img {object-position:50% 64%;}
    .cs-food-detail {width:48%;height:225px;left:0;bottom:0;transform:rotate(-7deg);animation-delay:.24s;}
    .cs-food-detail img {object-position:50% 79%;}
    .cs-image-label {position:absolute;bottom:12px;left:12px;right:12px;padding:11px;border-radius:14px;color:white;background:#18271d69;border:1px solid #ffffff30;backdrop-filter:blur(16px);font:500 11px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
    .cs-home-caption {display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:19px 4px 8px;color:#627362;font:400 12px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;animation:cs-arrive .8s .2s both;}
    .cs-home-caption strong {font-weight:600;color:#294635;}
    .st-key-home-actions {animation:cs-arrive .8s .25s both;}
    .st-key-home-actions button {border-radius:18px!important;min-height:54px;transition:transform .2s cubic-bezier(.2,.8,.2,1),box-shadow .2s ease;}
    .st-key-home-actions button:hover {transform:translateY(-3px);box-shadow:0 10px 24px #28443518;}
    .st-key-home-actions button:active {transform:scale(.97);}
    .cs-welcome {position:fixed;inset:0;z-index:99999;display:grid;place-content:center;justify-items:center;gap:16px;background:#f5f3ed;color:#233f31;pointer-events:none;animation:cs-welcome-away .45s .65s ease forwards;}
    .cs-welcome-mark {width:58px;height:58px;display:grid;place-content:center;border:1px solid #36564126;border-radius:20px;background:#fff9;box-shadow:0 10px 32px #233f3112;font:26px Georgia,serif;animation:cs-breathe .65s ease both;}
    .cs-welcome-name {font:22px Georgia,serif;}
    .cs-welcome-bar {width:70px;height:3px;background:#36564118;border-radius:9px;overflow:hidden;}
    .cs-welcome-bar::after {content:"";display:block;width:45%;height:100%;background:#365641;border-radius:9px;animation:cs-progress .7s ease-in-out infinite;}
    @keyframes cs-arrive {from {opacity:0;translate:0 18px;filter:blur(3px);}to {opacity:1;translate:0 0;filter:blur(0);}}
    @keyframes cs-settle {from {transform:scale(1.06);}to {transform:scale(1);}}
    @keyframes cs-breathe {from {opacity:0;transform:scale(.88);}to {opacity:1;transform:scale(1);}}
    @keyframes cs-progress {from {transform:translateX(-110%);}to {transform:translateX(320%);}}
    @keyframes cs-welcome-away {to {opacity:0;visibility:hidden;}}
    @media(max-width:900px) {.cs-hero {padding:30px;grid-template-columns:1fr;gap:20px;}.cs-hero h1 {font-size:48px;}.cs-photo-stack {height:280px;max-width:400px;width:100%;justify-self:center;}.cs-food-main {height:245px;width:63%;}.cs-food-detail {height:180px;width:43%;}}
    @media(max-width:480px) {.cs-hero {padding:26px 22px;border-radius:24px;}.cs-hero h1 {font-size:40px;}.cs-home-eyebrow {font-size:10px;margin-bottom:20px;}.cs-hero .cs-home-copy {font-size:14px;}.cs-photo-stack {height:245px;}.cs-food-main {height:218px;}.cs-food-detail {height:160px;}.cs-home-caption {font-size:11px;}}
    @media(prefers-reduced-motion:reduce) {.cs-hero,.cs-hero-bg,.cs-food-card,.cs-home-caption,.st-key-home-actions,.cs-welcome-mark {animation:none!important;}.cs-welcome {display:none;}.st-key-mainnav label,.st-key-home-actions button {transition:none!important;}.st-key-mainnav label:hover,.st-key-home-actions button:hover,.st-key-home-actions button:active {transform:none!important;}}
    </style>''')

def render_home():
    if not st.session_state.get('welcome_shown'):
        st.html('<div class="cs-welcome" aria-hidden="true"><div class="cs-welcome-mark">CS</div><div class="cs-welcome-name">Cocina de Siempre</div><div class="cs-welcome-bar"></div></div>')
        st.session_state.welcome_shown=True
    st.html(f'''<section class="cs-hero" aria-label="Bienvenido a Cocina de Siempre">
      <img class="cs-hero-bg" src="{photo('kitchen-bg.jpg')}" alt="" />
      <div><p class="cs-home-eyebrow">BIENVENIDO A CASA · COCINA DE SIEMPRE</p>
      <h1>La tradición<br>se sirve <em>cada día.</em></h1>
      <p class="cs-home-copy">Todo listo para un buen día. Tu carta, tus ventas y tu cocina, en un solo lugar.</p>
      <span class="cs-glass-tag"><span class="cs-dot"></span>Hecho con tradición. Llevado con cariño.</span></div>
      <div class="cs-photo-stack"><div class="cs-food-card cs-food-main"><img src="{photo('meal.jpg')}" alt="Plato servido en una sartén sobre una mesa de cocina" /><span class="cs-image-label">El sabor de lo hecho en casa</span></div>
      <div class="cs-food-card cs-food-detail"><img src="{photo('yogurt.jpg')}" alt="Bol de yogur con frutos rojos y una cuchara de madera" /><span class="cs-image-label">Los pequeños detalles cuentan</span></div></div>
      </section><div class="cs-home-caption"><span><strong>Tu restaurante, a tu ritmo.</strong> Elige por dónde empezar.</span><span>Cocina de Siempre / Local principal</span></div>''')
    def go(destination):
        st.session_state['mainnav']=destination
    with st.container(key='home-actions'):
        a,b,c=st.columns(3)
        a.button('Datos de venta',icon=':material/monitoring:',width='stretch',on_click=go,args=('Datos de venta',))
        b.button('Explorar la carta',icon=':material/restaurant_menu:',width='stretch',on_click=go,args=('Carta',))
        c.button('Ir a cocina',icon=':material/skillet:',width='stretch',on_click=go,args=('Cocina',))
