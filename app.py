import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import re
import plotly.express as px

# -------------------------
# Configuración página
# -------------------------
st.set_page_config(page_title="Validador de Dobles Cobros", page_icon="🚗", layout="wide")

# ==== CSS minimalista y profesional (claro) ====
st.markdown("""
<style>
/* App background and typography */
.stApp {
  background: #F7F9FB !important;
  color: #0F1724 !important;
  font-family: 'Inter', 'Segoe UI', Roboto, sans-serif;
}

/* Page title */
[data-testid="stHeader"] {display: none;} /* hide default header */
h1, h2, h3 { color: #0F1724 !important; font-weight: 600; }

/* Sidebar clean */
[data-testid="stSidebar"] {
  background: #FFFFFF !important;
  border-right: 1px solid #E6EEF3 !important;
  padding: 18px !important;
}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #0F1724 !important; }

/* Buttons */
.stButton button {
  background: linear-gradient(180deg,#0B7285,#046C67) !important; /* teal accent */
  color: #FFFFFF !important;
  border-radius: 10px !important;
  padding: 8px 14px !important;
  font-weight: 600 !important;
  box-shadow: none !important;
}
.stButton button:hover { transform: translateY(-1px); }

/* DataFrame / tables */
[data-testid="stDataFrame"] {
  background: #FFFFFF !important;
  border: 1px solid #E6EEF3 !important;
  border-radius: 8px !important;
  padding: 6px !important;
}

/* Cards / metrics */
.metric-card {
  background: #FFFFFF;
  border: 1px solid #E6EEF3;
  border-radius: 12px;
  padding: 14px;
}

/* Make charts area stand out slightly */
.chart-area {
  background: transparent;
  padding: 6px;
}

/* Small text styling */
.small-muted { color: #7A8A93; font-size: 13px; }

/* Tidy scrollbars */
::-webkit-scrollbar { height: 8px; width: 8px; }
::-webkit-scrollbar-thumb { background: #CBDDE3; border-radius: 10px; }

</style>
""", unsafe_allow_html=True)

# Title block (clean)
st.markdown("""
<div style='display:flex;align-items:center;gap:16px'>
  <img src='https://i.imgur.com/z9xt46F.jpeg' style='height:54px;border-radius:8px;object-fit:cover;'>
  <div>
    <h2 style='margin:0'>Validador de Dobles Cobros</h2>
    <div class='small-muted'>Interfaz profesional · Minimalista · Dashboard interactivo</div>
  </div>
</div>
<hr style='margin-top:12px;'>
""", unsafe_allow_html=True)

# -------------------------
# Helpers (misma lógica)
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
# Detección de posibles y confirmados
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
    # make sure timestamps are proper types for plotting
    confirmed['Fecha_entrada'] = pd.to_datetime(confirmed['Fecha_entrada'])
    confirmed['Fecha_salida']  = pd.to_datetime(confirmed['Fecha_salida'])

    return confirmed[['Nº de tarjeta','Transacción','Matrícula_clean','Placa_clean','Fecha_entrada','Fecha_salida','llave_validacion']]

# -------------------------
# Interfaz
# -------------------------

st.sidebar.header("Cargar archivos")
comercio_file = st.sidebar.file_uploader("Comercio (CSV o Excel)", type=['csv','xlsx','xls'])
gopass_file   = st.sidebar.file_uploader("Gopass (Excel)", type=['xlsx','xls'])

if comercio_file and gopass_file:
    try:
        with st.spinner("Cargando archivos..."):
            if comercio_file.name.lower().endswith('.csv'):
                comercio_df = pd.read_csv(comercio_file, sep=';', encoding='utf-8', engine='python')
            else:
                comercio_df = pd.read_excel(comercio_file)
            gopass_df = pd.read_excel(gopass_file)

        st.success("Archivos cargados")

        if st.button("Iniciar Validación"):
            comercio_filtered, comercio_keys = process_comercio_base(comercio_df)
            gopass_processed = process_gopass_base(gopass_df)

            possible_doubles = find_possible_doubles(comercio_keys, gopass_processed)
            confirmed = find_confirmed_doubles(possible_doubles, comercio_df)

            # SECTION: Resultados y dashboard
            st.subheader("Resumen")
            col1, col2, col3 = st.columns([1,1,2])

            total_possibles = 0 if possible_doubles is None or possible_doubles.empty else len(possible_doubles)
            total_confirmed = 0 if confirmed is None or confirmed.empty else len(confirmed)

            with col1:
                st.markdown("<div class='metric-card'><h3 style='margin:0'>{}</h3><div class='small-muted'>Posibles</div></div>".format(total_possibles), unsafe_allow_html=True)
            with col2:
                st.markdown("<div class='metric-card'><h3 style='margin:0'>{}</h3><div class='small-muted'>Confirmados</div></div>".format(total_confirmed), unsafe_allow_html=True)
            with col3:
                if total_confirmed > 0:
                    first_date = confirmed['Fecha_entrada'].min().strftime('%Y-%m-%d')
                    last_date = confirmed['Fecha_salida'].max().strftime('%Y-%m-%d')
                    st.markdown(f"<div class='metric-card'><div class='small-muted'>Rango de fechas</div><strong>{first_date} → {last_date}</strong></div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='metric-card'><div class='small-muted'>Rango de fechas</div><strong>—</strong></div>", unsafe_allow_html=True)

            st.markdown("---")

            if total_confirmed == 0:
                st.info("No se encontraron dobles cobros confirmados.")
            else:
                # Interactive charts
                st.subheader("Dashboard interactivo")
                # Chart 1: Conteo por placa
                counts = confirmed.groupby('Placa_clean').size().reset_index(name='count').sort_values('count', ascending=False)
                fig_bar = px.bar(counts, x='Placa_clean', y='count', labels={'Placa_clean':'Placa','count':'Cantidad'},
                                 title='Dobles cobros por placa', template='simple_white')
                fig_bar.update_layout(margin=dict(l=10,r=10,t=40,b=10))

                # Chart 2: Timeline (por entrada)
                timeline = confirmed.copy()
                timeline = timeline.sort_values('Fecha_entrada')
                fig_time = px.scatter(timeline, x='Fecha_entrada', y='Placa_clean', hover_data=['Nº de tarjeta','Transacción'],
                                      labels={'Fecha_entrada':'Fecha entrada','Placa_clean':'Placa'}, title='Timeline de transacciones (entrada)')
                fig_time.update_layout(margin=dict(l=10,r=10,t=40,b=10))

                # Chart 3: Tabla resumen (por matrícula si aplica)
                with st.container():
                    c1, c2 = st.columns([1,1])
                    with c1:
                        st.plotly_chart(fig_bar, use_container_width=True)
                    with c2:
                        st.plotly_chart(fig_time, use_container_width=True)

                st.markdown("---")
                st.subheader("Tabla de confirmados")
                st.dataframe(confirmed.reset_index(drop=True), use_container_width=True)

                # Download CSV
                csv = confirmed.to_csv(index=False).encode('utf-8')
                st.download_button("Descargar confirmados (CSV)", data=csv, file_name='dobles_confirmados.csv', mime='text/csv')

    except Exception as e:
        st.error(f"Error procesando archivos: {str(e)}")
else:
    st.info("Carga ambos archivos en la barra lateral para comenzar.")
