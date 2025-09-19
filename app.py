import streamlit as st 
import pandas as pd
import numpy as np
from datetime import datetime
import re
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# -------------------------
# Configuración página
# -------------------------
st.set_page_config(page_title="Validador de Dobles Cobros", page_icon="🚗", layout="wide")
st.title("🚗 Validador de Dobles Cobros")
st.markdown("---")

# ===== CSS Personalizado =====
st.markdown("""
<style>
/* Fondo principal */
.main {
    background-color: #0E1117;
}

/* Sidebar con colores que combinan con el logo GoPass */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1f35 0%, #2d1f35 100%) !important;
    color: white !important;
    width: 300px !important;
    padding: 20px 10px !important;
    border-right: 1px solid #444 !important;
}

[data-testid="stSidebar"] h1, 
[data-testid="stSidebar"] h2, 
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stCheckbox label {
    color: white !important; 
}

[data-testid="stSidebar"] .stFileUploader > label {
    color: white !important;
    font-weight: bold;
}

[data-testid="stSidebar"] .uppy-Dashboard-AddFiles-list button span:first-child {
    font-size: 0 !important;
}

[data-testid="stSidebar"] .uppy-Dashboard-AddFiles-list button span:first-child::after {
    content: "Buscar archivo" !important;
    font-size: 14px !important;
    color: white !important;
    background-color: #4a2c7e;
    padding: 8px 12px;
    border-radius: 4px;
    font-weight: bold !important;
}

/* Botones */
.stButton > button {
    background-color: #4a2c7e !important;
    color: white !important;
    border: none;
    border-radius: 6px;
    padding: 10px 24px;
    font-weight: bold;
    transition: all 0.3s ease;
}

.stButton > button:hover {
    background-color: #6b3dad !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}

/* Títulos y texto */
h1, h2, h3 {
    color: #4a2c7e !important;
}

/* Dataframes */
.dataframe {
    border-radius: 8px;
    overflow: hidden;
}

/* Tarjetas de métricas */
.css-1r6slb0 {
    background-color: #f0f2f6;
    border-radius: 8px;
    padding: 15px;
    border-left: 4px solid #4a2c7e;
}

/* Progress bar */
.stProgress > div > div {
    background-color: #4a2c7e;
}

/* Alertas */
.stAlert {
    border-radius: 8px;
}

/* Logo container */
.logo-container {
    display: flex;
    justify-content: center;
    margin-bottom: 30px;
    background: rgba(255, 255, 255, 0.1);
    padding: 15px;
    border-radius: 12px;
    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
}
</style>
""", unsafe_allow_html=True)

# Logo de GoPass con contenedor estilizado
st.markdown("""
<div class="logo-container">
    <img src="https://i.imgur.com/z9xt46F.jpeg"
         style="width: 60%; border-radius: 10px; display: block; margin: 0 auto;" 
         alt="Logo Gopass">
</div>
""", unsafe_allow_html=True)

# -------------------------
# Helpers
# -------------------------
def clean_colnames(df):
    df.columns = [str(c).strip() for c in df.columns]
    return df

def normalize_datetime_vectorized(date_series):
    s = date_series.astype(str).str.strip().replace({'nan': None})
    s = s.str.replace(r'\s+', ' ', regex=True)
    s = s.str.replace(r'\ba\.?\s*m\.?\b', 'AM', flags=re.IGNORECASE, regex=True)
    s = s.str.replace(r'\bp\.?\s*m\.?\b', 'PM', flags=re.IGNORECASE, regex=True)
    parsed = pd.to_datetime(s, dayfirst=True, errors='coerce')
    return parsed

def make_validation_key(dt_entry, dt_exit):
    e = dt_entry.dt.strftime("%Y-%m-%d %H")
    x = dt_exit.dt.strftime("%Y-%m-%d %H")
    return e + "|" + x

def plate_is_valid(plate):
    if pd.isna(plate):
        return False
    p = str(plate).strip().upper()
    return bool(re.match(r'^[A-Z]{3}\d{3}$', p))

# -------------------------
# Procesamiento Base Comercio
# -------------------------
def process_comercio_base(df):
    df = clean_colnames(df)
    required_cols = ['Nº de tarjeta', 'Tarjeta', 'Movimiento', 'Fecha/Hora', 'Matrícula']
    miss = [c for c in required_cols if c not in df.columns]
    if miss:
        raise ValueError(f"Faltan columnas en la base del comercio: {miss}")

    df['Fecha/Hora_normalizada'] = normalize_datetime_vectorized(df['Fecha/Hora'])
    df['Movimiento_norm'] = df['Movimiento'].astype(str).str.strip().str.lower()
    df['Movimiento_norm'] = df['Movimiento_norm'].replace({
        'entrada': 'Entrada', 'salida': 'Salida', 'transacción': 'Transacción', 'transaccion': 'Transacción'
    })

    df['Tarjeta_norm'] = df['Tarjeta'].astype(str).str.strip()
    df_filtered = df[df['Tarjeta_norm'].isin(['TiqueteVehiculo', 'Una salida 01'])].copy()

    tmp = df_filtered.dropna(subset=['Fecha/Hora_normalizada']).copy()
    if tmp.empty:
        return df_filtered, pd.DataFrame(columns=['Nº de tarjeta','Fecha_entrada','Fecha_salida','llave_validacion'])

    entradas = tmp[tmp['Movimiento_norm'] == 'Entrada'].groupby('Nº de tarjeta', as_index=False)['Fecha/Hora_normalizada'].min().rename(columns={'Fecha/Hora_normalizada':'Fecha_entrada'})
    salidas  = tmp[tmp['Movimiento_norm'] == 'Salida'].groupby('Nº de tarjeta', as_index=False)['Fecha/Hora_normalizada'].max().rename(columns={'Fecha/Hora_normalizada':'Fecha_salida'})

    comercio_keys = entradas.merge(salidas, on='Nº de tarjeta', how='inner')
    if comercio_keys.empty:
        return df_filtered, pd.DataFrame(columns=['Nº de tarjeta','Fecha_entrada','Fecha_salida','llave_validacion'])

    comercio_keys['llave_validacion'] = make_validation_key(comercio_keys['Fecha_entrada'], comercio_keys['Fecha_salida'])
    return df_filtered, comercio_keys[['Nº de tarjeta','Fecha_entrada','Fecha_salida','llave_validacion']]

# -------------------------
# Procesamiento Base Gopass
# -------------------------
def process_gopass_base(df):
    df = clean_colnames(df)
    required_cols = ['Fecha de entrada', 'Fecha de salida', 'Transacción', 'Placa Vehiculo']
    miss = [c for c in required_cols if c not in df.columns]
    if miss:
        raise ValueError(f"Faltan columnas en la base de Gopass: {miss}")

    df['Fecha_entrada_norm_full'] = normalize_datetime_vectorized(df['Fecha de entrada'])
    df['Fecha_salida_norm_full']  = normalize_datetime_vectorized(df['Fecha de salida'])
    df['llave_validacion'] = make_validation_key(df['Fecha_entrada_norm_full'], df['Fecha_salida_norm_full'])
    df['Transacción'] = df['Transacción'].astype(str).str.strip()
    df['Placa_clean'] = df['Placa Vehiculo'].astype(str).str.strip().str.upper()

    df_valid = df.dropna(subset=['Fecha_entrada_norm_full','Fecha_salida_norm_full']).copy()
    return df_valid

# -------------------------
# Buscar posibles dobles cobros
# -------------------------
def find_possible_doubles(comercio_keys, gopass_df):
    merged = comercio_keys.merge(
        gopass_df[['Transacción','Fecha_entrada_norm_full','Fecha_salida_norm_full','llave_validacion','Placa_clean']],
        on='llave_validacion', how='inner', suffixes=('_comercio','_gopass')
    )
    if merged.empty:
        return pd.DataFrame()

    merged['dif_entrada'] = (merged['Fecha_entrada'] - merged['Fecha_entrada_norm_full']).dt.total_seconds()/60
    merged['dif_salida']  = (merged['Fecha_salida'] - merged['Fecha_salida_norm_full']).dt.total_seconds()/60

    possibles = merged[(merged['dif_entrada'].between(-5,5)) & (merged['dif_salida'].between(-5,5))].copy()
    return possibles

# -------------------------
# Confirmar dobles cobros
# -------------------------
def find_confirmed_doubles(possible_df, comercio_df_original):
    if possible_df is None or possible_df.empty:
        return pd.DataFrame()

    comercio_df_original['Matrícula_clean'] = comercio_df_original['Matrícula'].astype(str).str.strip().str.upper()
    comercio_valid_plates = comercio_df_original[comercio_df_original['Matrícula_clean'].apply(plate_is_valid)][['Nº de tarjeta','Matrícula_clean']].drop_duplicates()

    merged = possible_df.merge(comercio_valid_plates, on='Nº de tarjeta', how='inner')
    if merged.empty:
        return pd.DataFrame()

    merged['llave_confirmacion_comercio'] = merged['llave_validacion'] + "|" + merged['Matrícula_clean']
    merged['llave_confirmacion_gopass']   = merged['llave_validacion'] + "|" + merged['Placa_clean']

    confirmed = merged[merged['llave_confirmacion_comercio'] == merged['llave_confirmacion_gopass']].copy()

    return confirmed[['Nº de tarjeta','Transacción','Matrícula_clean','Placa_clean','llave_validacion','llave_confirmacion_comercio','llave_confirmacion_gopass']]

# -------------------------
# Interfaz
# -------------------------
st.sidebar.header("📁 Cargar Archivos")

comercio_file = st.sidebar.file_uploader("Cargar archivo del Comercio (CSV o Excel)", type=['csv','xlsx','xls'])
gopass_file   = st.sidebar.file_uploader("Cargar archivo de Gopass (Excel)", type=['xlsx','xls'])

if comercio_file and gopass_file:
    try:
        with st.spinner("Cargando archivo Comercio..."):
            if comercio_file.name.lower().endswith('.csv'):
                comercio_df = pd.read_csv(comercio_file, sep=';', encoding='utf-8', engine="python")
            else:
                comercio_df = pd.read_excel(comercio_file)

        with st.spinner("Cargando archivo Gopass..."):
            gopass_df = pd.read_excel(gopass_file)

        st.success("✅ Archivos cargados correctamente")

        if st.button("🚀 Iniciar Validación de Dobles Cobros", type="primary"):
            with st.spinner("Procesando datos..."):
                comercio_filtered, comercio_keys = process_comercio_base(comercio_df)
                gopass_processed = process_gopass_base(gopass_df)

                possible_doubles = find_possible_doubles(comercio_keys, gopass_processed)
                
                # Mostrar métricas iniciales
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Registros Comercio", len(comercio_df))
                with col2:
                    st.metric("Registros GoPass", len(gopass_df))
                with col3:
                    st.metric("Posibles Dobles Cobros", len(possible_doubles))
                
                if possible_doubles.empty:
                    st.success("✅ No se encontraron posibles dobles cobros.")
                else:
                    st.subheader("⚠️ Posibles Dobles Cobros")
                    st.dataframe(possible_doubles, use_container_width=True)

                    confirmed = find_confirmed_doubles(possible_doubles, comercio_df)
                    
                    col4, col5 = st.columns(2)
                    with col4:
                        st.metric("Dobles Cobros Confirmados", len(confirmed))
                    with col5:
                        st.metric("Falsos Positivos", len(possible_doubles) - len(confirmed))
                    
                    if confirmed.empty:
                        st.info("No se encontraron dobles cobros confirmados.")
                    else:
                        st.subheader("🚨 Dobles Cobros Confirmados")
                        st.dataframe(confirmed, use_container_width=True)

                        # -------------------------
                        # MINI DASHBOARD
                        # -------------------------
                        st.markdown("---")
                        st.header("📊 Dashboard de Resultados")

                        col1, col2 = st.columns(2)

                        # Gráfico 1: Totales de registros en bases originales
                        with col1:
                            base_counts = pd.DataFrame({
                                "Base": ["Comercio", "GoPass"],
                                "Registros": [len(comercio_df), len(gopass_df)]
                            })
                            fig1 = px.bar(base_counts, x="Base", y="Registros", text="Registros",
                                        color="Base", 
                                        color_discrete_sequence=["#4a2c7e", "#6b3dad"],
                                        title="Cantidad de registros por base")
                            fig1.update_traces(textposition="outside")
                            fig1.update_layout(plot_bgcolor='rgba(0,0,0,0)')
                            st.plotly_chart(fig1, use_container_width=True)

                        # Gráfico 2: Proporción de dobles cobros confirmados
                        with col2:
                            total_confirmados = len(confirmed)
                            total_no_confirmados = len(possible_doubles) - total_confirmados
                            pie_data = pd.DataFrame({
                                "Categoria": ["Confirmados", "No Confirmados"],
                                "Cantidad": [total_confirmados, total_no_confirmados]
                            })
                            fig2 = px.pie(pie_data, names="Categoria", values="Cantidad", hole=0.5,
                                        color_discrete_sequence=["#4a2c7e", "#9d71c6"],
                                        title="Proporción de dobles cobros confirmados")
                            fig2.update_traces(textinfo='percent+label')
                            st.plotly_chart(fig2, use_container_width=True)

    except Exception as e:
        st.error(f"Error procesando archivos: {str(e)}")
else:
    st.info("👆 Carga ambos archivos en la barra lateral para comenzar.")
