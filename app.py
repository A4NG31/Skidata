import streamlit as st 
import pandas as pd
import numpy as np
from datetime import datetime
import re

# -------------------------
# Configuración página
# -------------------------
st.set_page_config(page_title="Validador de Dobles Cobros", page_icon="🚗", layout="wide")

# =========================
# Estilos CSS - UI moderno
# =========================
st.markdown("""
<style>
/* --- Global app background and font --- */
:root{
    --bg:#0f1720;         /* very dark blue/gray */
    --card:#11121a;       /* card background */
    --muted:#9aa6b2;      /* muted text */
    --accent:#00cfff;     /* primary accent - cyan */
    --accent-2:#00b894;   /* secondary - teal */
    --glass: rgba(255,255,255,0.03);
}

body, .css-1d391kg, .reportview-container .main {
    background: linear-gradient(180deg, var(--bg) 0%, #0b1220 100%) !important;
    color: #e6eef6 !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;
}

/* --- Sidebar fixed and styled --- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1116, #12141a) !important;
    border-right: 1px solid rgba(255,255,255,0.03) !important;
    width: 320px !important;
    padding: 26px !important;
    position: fixed !important;        /* keep sidebar fixed */
    height: 100vh !important;
    overflow: auto !important;
}

/* Hide the collapse button so sidebar can't be hidden */
[data-testid="stSidebarNav"] button { display: none !important; }

/* Sidebar headings and text */
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p {
    color: #dff7ff !important;
}
[data-testid="stSidebar"] h1 { color: var(--accent) !important; font-weight:700 !important; }

/* File uploader area styling */
[data-testid="stSidebar"] .uppy-Dashboard-AddFiles {
    background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)) !important;
    border: 1px dashed rgba(255,255,255,0.06) !important;
    padding: 14px !important;
    border-radius: 10px !important;
}

/* Browse button */
[data-testid="stSidebar"] .uppy-Dashboard-AddFiles-list button {
    background: linear-gradient(90deg, var(--accent), var(--accent-2)) !important;
    color: #022028 !important;
    font-weight: 700 !important;
    border: none !important;
    padding: 8px 14px !important;
    border-radius: 8px !important;
    box-shadow: 0 6px 18px rgba(0,200,255,0.08) !important;
}
[data-testid="stSidebar"] .uppy-Dashboard-AddFiles-list button:hover{ transform: translateY(-2px); }

/* Sidebar small labels */
[data-testid="stSidebar"] label, [data-testid="stSidebar"] .stMarkdown p {
    color: var(--muted) !important;
}

/* Inputs look like cards */
[data-testid="stSidebar"] .stTextInput > div, [data-testid="stSidebar"] .stSelectbox > div, [data-testid="stSidebar"] .stMultiSelect > div {
    background: var(--card) !important;
    border-radius: 8px !important;
    padding: 6px 10px !important;
    color: #e6eef6 !important;
}

/* Main area - leave space for fixed sidebar */
.css-1d391kg .main > div:first-child {
    margin-left: 360px !important; /* give room for sidebar */
}

/* Header */
.app-header{
    display:flex; align-items:center; justify-content:space-between;
    gap: 12px; margin-bottom: 8px;
}
.app-title{ font-size:28px; font-weight:800; color: #eafcff; }
.app-sub{ color: var(--muted); font-size:13px; }

/* Card / panel style for results */
.card {
    background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
    border-radius: 12px; padding: 18px; margin-bottom: 16px;
    box-shadow: 0 6px 20px rgba(2,12,27,0.6);
    border: 1px solid rgba(255,255,255,0.03);
}

/* Accent buttons */
.stButton>button {
    background: linear-gradient(90deg, var(--accent), var(--accent-2)) !important;
    color: #022028 !important; font-weight:700; padding: 10px 18px; border-radius: 10px; border: none;
}
.stButton>button:hover{ transform: translateY(-2px); }

/* Dataframe container (streamlit) */
.element-container .stDataFrame, .stDataFrame {
    border-radius: 10px !important; overflow: hidden !important;
}

/* Table header accent */
.stDataFrame thead tr th{ background: linear-gradient(90deg, rgba(0,200,255,0.08), rgba(0,184,148,0.06)) !important; }

/* Make messages (success, info, error) cleaner */
.stAlert {
    border-radius: 10px !important;
}

/* Small responsive tweaks */
@media (max-width: 900px){
    [data-testid="stSidebar"]{ position: relative; width:100% !important; height:auto !important; }
    .css-1d391kg .main > div:first-child { margin-left: 0 !important; }
}

</style>
""", unsafe_allow_html=True)

# Logo de GoPass con HTML (mejor posicionado)
st.markdown("""
<div style="display:flex; align-items:center; gap:12px; margin-bottom:22px;">
    <img src="https://i.imgur.com/z9xt46F.jpeg" style="width:64px; height:64px; border-radius:12px; box-shadow:0 8px 24px rgba(0,0,0,0.6);" alt="Logo Gopass">
    <div>
        <div class="app-title">🚗 Validador de Dobles Cobros</div>
        <div class="app-sub">Interfaz limpia — detecta posibles y confirmados con tolerancia de tiempo</div>
    </div>
</div>
""", unsafe_allow_html=True)

# -------------------------
# Helpers (sin cambios relevantes)
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
# Buscar posibles dobles cobros (con tolerancia)
# -------------------------

def find_possible_doubles(comercio_keys, gopass_df):
    st.info("🔍 Buscando posibles dobles cobros (±5 min)...")

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
with st.sidebar:
    st.header("📁 Cargar Archivos")
    comercio_file = st.file_uploader("Cargar archivo del Comercio (CSV o Excel)", type=['csv','xlsx','xls'])
    gopass_file   = st.file_uploader("Cargar archivo de Gopass (Excel)", type=['xlsx','xls'])
    st.markdown("---")
    st.caption("Formato esperado: columnas mínimas en cada archivo. Revisa mensajes de error si algo falta.")

# Cuerpo principal
st.markdown("""
<div class="card">
    <strong>Instrucciones rápidas:</strong>
    <ul>
        <li>Sube los archivos en la barra lateral. El CSV de comercio puede usar separador punto y coma.</li>
        <li>Presiona <em>Iniciar Validación</em> para ver posibles y confirmados.</li>
        <li>Los resultados muestran tolerancia de ±5 minutos entre registros.</li>
    </ul>
</div>
""", unsafe_allow_html=True)

if 'comercio_file' not in locals():
    comercio_file = None
if 'gopass_file' not in locals():
    gopass_file = None

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

        if st.button("🚀 Iniciar Validación de Dobles Cobros"):
            comercio_filtered, comercio_keys = process_comercio_base(comercio_df)
            gopass_processed = process_gopass_base(gopass_df)

            possible_doubles = find_possible_doubles(comercio_keys, gopass_processed)
            if possible_doubles.empty:
                st.success("✅ No se encontraron posibles dobles cobros.")
            else:
                st.markdown('<div class="card"><h3>⚠️ Posibles Dobles Cobros</h3></div>', unsafe_allow_html=True)
                st.dataframe(possible_doubles, use_container_width=True)

                confirmed = find_confirmed_doubles(possible_doubles, comercio_df)
                if confirmed.empty:
                    st.info("No se encontraron dobles cobros confirmados.")
                else:
                    st.markdown('<div class="card"><h3>🚨 Dobles Cobros Confirmados</h3></div>', unsafe_allow_html=True)
                    st.dataframe(confirmed, use_container_width=True)

    except Exception as e:
        st.error(f"Error procesando archivos: {str(e)}")
else:
    st.info("👆 Carga ambos archivos en la barra lateral para comenzar.")

# Footer small note
st.markdown("<div style='margin-top:14px;color:var(--muted);font-size:12px'>Powered by GoPass • Interfaz optimizada</div>", unsafe_allow_html=True)
