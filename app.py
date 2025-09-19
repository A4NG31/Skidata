import streamlit as st 
import pandas as pd
import numpy as np
from datetime import datetime
import re

# -------------------------
# Configuración página
# -------------------------
st.set_page_config(page_title="Validador de Dobles Cobros", page_icon="🚗", layout="wide")
st.title("🚗 Validador de Dobles Cobros")
st.markdown("---")

# ===== CSS GLOBAL =====
st.markdown("""
<style>
/* ===== Fondo General ===== */
.stApp {
    background: linear-gradient(135deg, #0F2027, #203A43, #2C5364);
    color: white !important;
    font-family: 'Segoe UI', sans-serif;
}

/* ===== Títulos ===== */
h1, h2, h3, h4 {
    color: #00F5D4 !important;
    font-weight: bold !important;
    text-shadow: 0px 0px 8px rgba(0, 245, 212, 0.5);
}

/* ===== Separadores ===== */
hr {
    border: 1px solid #00CFFF !important;
}

/* ===== Sidebar ===== */
[data-testid="stSidebar"] {
    background-color: #1E1E2F !important;
    padding: 20px 10px 20px 10px !important;
    border-right: 1px solid #333 !important;
}

/* Texto en sidebar */
[data-testid="stSidebar"] h1, 
[data-testid="stSidebar"] h2, 
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label {
    color: #E0E0E0 !important; 
}

/* Botón expandir sidebar */
[data-testid="stSidebarNav"] button {
    background: #2E2E3E !important;
    color: white !important;
    border-radius: 6px !important;
}

/* ===== DataFrames estilo glass ===== */
[data-testid="stDataFrame"] {
    background: rgba(255, 255, 255, 0.05) !important;
    border-radius: 12px !important;
    box-shadow: 0px 0px 12px rgba(0,0,0,0.4);
}

/* ===== Botones ===== */
.stButton button {
    background: linear-gradient(90deg, #00CFFF, #00F5D4);
    color: black !important;
    font-weight: bold;
    border-radius: 12px;
    padding: 10px 20px;
    border: none;
    transition: 0.3s ease-in-out;
}
.stButton button:hover {
    background: linear-gradient(90deg, #00F5D4, #00CFFF);
    transform: scale(1.05);
    box-shadow: 0px 0px 10px rgba(0,245,212,0.6);
}

/* ===== Scrollbar ===== */
::-webkit-scrollbar {
    width: 8px;
}
::-webkit-scrollbar-track {
    background: #1E1E2F;
}
::-webkit-scrollbar-thumb {
    background: #00CFFF;
    border-radius: 10px;
}
::-webkit-scrollbar-thumb:hover {
    background: #00F5D4;
}
</style>
""", unsafe_allow_html=True)

# Logo de GoPass
st.markdown("""
<div style="display: flex; justify-content: center; margin-bottom: 30px;">
    <img src="https://i.imgur.com/z9xt46F.jpeg"
         style="width: 40%; border-radius: 15px; box-shadow: 0px 0px 12px rgba(0,245,212,0.5);" 
         alt="Logo Gopass">
</div>
""", unsafe_allow_html=True)

# -------------------------
# Helpers (no modifiqué lógica)
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
# Procesamiento (igual)
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

def find_possible_doubles(comercio_keys, gopass_df):
    st.write("🔍 Buscando posibles dobles cobros (±5 min)...")

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

        if st.button("🚀 Iniciar Validación de Dobles Cobros"):
            comercio_filtered, comercio_keys = process_comercio_base(comercio_df)
            gopass_processed = process_gopass_base(gopass_df)

            possible_doubles = find_possible_doubles(comercio_keys, gopass_processed)
            if possible_doubles.empty:
                st.success("✅ No se encontraron posibles dobles cobros.")
            else:
                st.subheader("⚠️ Posibles Dobles Cobros")
                st.dataframe(possible_doubles, use_container_width=True)

                confirmed = find_confirmed_doubles(possible_doubles, comercio_df)
                if confirmed.empty:
                    st.info("ℹ️ No se encontraron dobles cobros confirmados.")
                else:
                    st.subheader("🚨 Dobles Cobros Confirmados")
                    st.dataframe(confirmed, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error procesando archivos: {str(e)}")
else:
    st.info("👆 Carga ambos archivos en la barra lateral para comenzar.")
