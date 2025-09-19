import pandas as pd
import streamlit as st
import io
from openpyxl import load_workbook
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuración de página
st.set_page_config(
    page_title="GoPass - Validador Terpel", 
    page_icon="⛽", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================================
# 🎨 CSS personalizado GoPass
# ================================
st.markdown("""
<style>
    :root {
        --gopass-blue: #1E3A8A;
        --gopass-light-blue: #3B82F6;
        --gopass-orange: #F59E0B;
        --gopass-green: #10B981;
        --gopass-red: #EF4444;
        --gopass-gray: #6B7280;
        --gopass-light-gray: #F3F4F6;
    }

    header[data-testid="stHeader"], .stDeployButton {display: none;}
    .stMainBlockContainer {padding-top: 1rem;}

    .main-header {
        background: linear-gradient(135deg, var(--gopass-blue), var(--gopass-light-blue));
        color: white;
        padding: 2rem 0;
        margin: -1rem -1rem 2rem -1rem;
        text-align: center;
        border-radius: 0 0 20px 20px;
        box-shadow: 0 4px 20px rgba(30, 58, 138, 0.3);
    }
    .main-title {font-size: 2.5rem; font-weight: 700; margin-bottom: .5rem; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);}
    .main-subtitle {font-size: 1.2rem; opacity: .9; font-weight: 300;}

    .metric-card {
        background: white; padding: 1.5rem; border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,.1);
        border-left: 4px solid var(--gopass-light-blue);
        margin-bottom: 1rem;
    }
    .metric-value {font-size: 2rem; font-weight: 700; color: var(--gopass-blue);}
    .metric-label {font-size: .9rem; color: var(--gopass-gray); font-weight: 500;}

    .status-normal {background: var(--gopass-green); color: white; padding: .25rem .75rem; border-radius: 20px;}
    .status-doble {background: var(--gopass-red); color: white; padding: .25rem .75rem; border-radius: 20px;}

    .custom-info {background: rgba(59, 130, 246, .1); border-left: 4px solid var(--gopass-light-blue); padding: 1rem 1.5rem; border-radius: 10px; margin: 1rem 0;}
    .custom-success {background: rgba(16,185,129,.1); border-left: 4px solid var(--gopass-green); padding: 1rem 1.5rem; border-radius: 10px; margin: 1rem 0; color: var(--gopass-green);}
    .custom-warning {background: rgba(245,158,11,.1); border-left: 4px solid var(--gopass-orange); padding: 1rem 1.5rem; border-radius: 10px; margin: 1rem 0; color: var(--gopass-orange);}

    .footer {text-align: center; padding: 2rem 0; margin-top: 3rem; border-top: 1px solid var(--gopass-light-gray); color: var(--gopass-gray);}
</style>
""", unsafe_allow_html=True)

# ================================
# 🏷️ Header
# ================================
st.markdown("""
<div class="main-header">
    <img src="https://i.imgur.com/z9xt46F.jpeg" 
         style="width: 200px; border-radius: 15px; margin-bottom: 1rem; box-shadow: 0 4px 15px rgba(0,0,0,.3);" 
         alt="Logo GoPass">
    <div class="main-title">⛽ Validador de Dobles Cobros</div>
    <div class="main-subtitle">Gasolineras Terpel - Sistema de Detección Avanzada</div>
</div>
""", unsafe_allow_html=True)

# ================================
# 📂 Carga de archivo
# ================================
uploaded_file = st.file_uploader(
    "Selecciona el archivo de transacciones Terpel",
    type=['xlsx'],
    help="Archivo Excel con las transacciones de gasolineras Terpel",
    accept_multiple_files=False
)

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df['Fecha de Pago'] = pd.to_datetime(df['Fecha de Pago'], dayfirst=True, errors='coerce')
    df = df[(df['Valor Pagado'] > 0) & (df['Estado'] == 'Exitosa')].copy()
    df['Novedad'] = "NORMAL"

    # Detectar dobles cobros
    df.sort_values(by=['Establecimiento','Placa','Valor Pagado','Fecha de Pago'], inplace=True)
    for i in range(1, len(df)):
        cond = (
            df.iloc[i]['Establecimiento'] == df.iloc[i-1]['Establecimiento'] and
            df.iloc[i]['Placa'] == df.iloc[i-1]['Placa'] and
            df.iloc[i]['Valor Servicio'] == df.iloc[i-1]['Valor Servicio'] and
            df.iloc[i]['Valor Pagado'] == df.iloc[i-1]['Valor Pagado'] and
            df.iloc[i]['Id'] != df.iloc[i-1]['Id'] and
            abs((df.iloc[i]['Fecha de Pago'] - df.iloc[i-1]['Fecha de Pago']).total_seconds()) <= 600
        )
        if cond:
            df.at[i,'Novedad'] = "DOBLE COBRO"
            df.at[i-1,'Novedad'] = "DOBLE COBRO"

    # ================================
    # 📊 Estadísticas
    # ================================
    total = len(df)
    dobles = len(df[df['Novedad']=="DOBLE COBRO"])
    normales = total - dobles
    valor_dobles = df[df['Novedad']=="DOBLE COBRO"]['Valor Pagado'].sum()
    porc_dobles = (dobles/total*100) if total>0 else 0

    col1,col2,col3,col4,col5 = st.columns(5)
    col1.metric("TOTAL REGISTROS", f"{total:,}".replace(",","."))
    col2.metric("DOBLES COBROS", f"{dobles:,}".replace(",","."))
    col3.metric("% DOBLES", f"{porc_dobles:.2f}%")
    col4.metric("NORMALES", f"{normales:,}".replace(",","."))
    col5.metric("VALOR DOBLES", f"${valor_dobles:,.0f}".replace(",", "."))

    # ================================
    # 📈 Gráficas
    # ================================
    col1, col2 = st.columns(2)
    with col1:
        fig_dona = go.Figure(go.Pie(
            labels=['Normales','Dobles'],
            values=[normales,dobles],
            hole=.6,
            marker_colors=['#10B981','#EF4444']
        ))
        fig_dona.update_layout(title="Distribución de Registros", title_x=0.5, height=300)
        st.plotly_chart(fig_dona, use_container_width=True)

    with col2:
        if dobles>0:
            top_est = df[df['Novedad']=="DOBLE COBRO"]['Establecimiento'].value_counts().head(10)
            fig_bar = px.bar(
                x=top_est.values,
                y=top_est.index,
                orientation="h",
                title="Top 10 Establecimientos con Dobles Cobros",
                color=top_est.values,
                color_continuous_scale=['#F59E0B','#EF4444']
            )
            fig_bar.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

    # Vista previa
    st.markdown("### 📋 Vista Previa de Datos")
    st.dataframe(df.head(100), use_container_width=True, height=400)

# ================================
# 📌 Footer
# ================================
st.markdown("""
<div class="footer">
    🚀 GoPass Analytics Platform | Validador Terpel v2.0 <br>
    Desarrollado por <b>Angel Torres</b> © 2025
</div>
""", unsafe_allow_html=True)
