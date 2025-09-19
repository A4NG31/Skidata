import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re

# -------------------------
# Configuración página
# -------------------------
st.set_page_config(page_title="Validador de Dobles Cobros", page_icon="🚗", layout="wide")
st.title("🚗 Validador de Dobles Cobros")
st.markdown("---")

# -------------------------
# Helpers
# -------------------------
def clean_colnames(df):
    df.columns = [str(c).strip() for c in df.columns]
    return df

def normalize_datetime_vectorized(date_series):
    """
    Normaliza cadenas de fecha como '1/09/2025  12:03:53 a. m.' o '15/09/2025 9:37:34 p. m.' a datetime.
    """
    s = date_series.astype(str).str.strip().replace({'nan': None})
    # limpiar espacios múltiples
    s = s.str.replace(r'\s+', ' ', regex=True)
    # convertir formatos con a.m./p.m. escritos como 'a. m.' o 'p. m.'
    s = s.str.replace(r'\ba\.?\s*m\.?\b', 'AM', flags=re.IGNORECASE, regex=True)
    s = s.str.replace(r'\bp\.?\s*m\.?\b', 'PM', flags=re.IGNORECASE, regex=True)
    # intentar parse vectorizado
    parsed = pd.to_datetime(s, dayfirst=True, errors='coerce')
    return parsed

def make_validation_key(dt_entry, dt_exit):
    """
    Llave de validación: usamos año-mes-día hora (sin minutos/segundos) en formato ISO para consistencia.
    """
    e = dt_entry.dt.strftime("%Y-%m-%d %H")
    x = dt_exit.dt.strftime("%Y-%m-%d %H")
    return e + "|" + x

def plate_is_valid(plate):
    """
    Valida matrícula: 6 caracteres, primeros 3 letras, últimos 3 números.
    """
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

    # Normalizar fechas
    df['Fecha/Hora_normalizada'] = normalize_datetime_vectorized(df['Fecha/Hora'])
    # Normalizar Movimiento (quitar espacios, minus/Mayus)
    df['Movimiento_norm'] = df['Movimiento'].astype(str).str.strip().str.lower()
    # mapear variantes comunes a 'Entrada','Salida','Transacción'
    df['Movimiento_norm'] = df['Movimiento_norm'].replace({
        'entrada': 'entrada', 'entrada ': 'entrada', 'entrada\r': 'entrada',
        'salida': 'salida', 'salida ': 'salida',
        'transacción': 'transaccion', 'transaccion': 'transaccion', 'transacción ': 'transaccion'
    })
    # mantener formato capitalizado
    df['Movimiento_norm'] = df['Movimiento_norm'].map({
        'entrada': 'Entrada',
        'salida': 'Salida',
        'transaccion': 'Transacción'
    }).fillna(df['Movimiento'].astype(str).str.strip())

    # Filtrar Tarjeta
    df['Tarjeta_norm'] = df['Tarjeta'].astype(str).str.strip()
    df_filtered = df[df['Tarjeta_norm'].isin(['TiqueteVehiculo', 'Una salida 01'])].copy()

    # Agrupar por Nº de tarjeta: obtener fecha entrada (min) y salida (max) por tarjeta
    # Solo considerar registros con Fecha/Hora_normalizada no nula
    tmp = df_filtered.dropna(subset=['Fecha/Hora_normalizada']).copy()
    if tmp.empty:
        return df_filtered, pd.DataFrame(columns=['Nº de tarjeta','Fecha_entrada','Fecha_salida','llave_validacion'])

    entradas = tmp[tmp['Movimiento_norm'] == 'Entrada'].groupby('Nº de tarjeta', as_index=False)['Fecha/Hora_normalizada'].min().rename(columns={'Fecha/Hora_normalizada':'Fecha_entrada'})
    salidas  = tmp[tmp['Movimiento_norm'] == 'Salida'].groupby('Nº de tarjeta', as_index=False)['Fecha/Hora_normalizada'].max().rename(columns={'Fecha/Hora_normalizada':'Fecha_salida'})

    comercio_keys = entradas.merge(salidas, on='Nº de tarjeta', how='inner')
    if comercio_keys.empty:
        # si no hay pares entrada/salida, informar movimientos existentes para debug
        movimientos_unicos = sorted(tmp['Movimiento_norm'].unique())
        raise ValueError(f"No se encontraron pares Entrada/Salida por 'Nº de tarjeta'. Movimientos disponibles: {movimientos_unicos}")

    # crear llave de validación (hora precision)
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

    # crear llave en mismo formato (YYYY-MM-DD HH)
    df['llave_validacion'] = make_validation_key(df['Fecha_entrada_norm_full'], df['Fecha_salida_norm_full'])
    # limpiar Transacción y Placa para merges posteriores
    df['Transacción'] = df['Transacción'].astype(str).str.strip()
    df['Placa_clean'] = df['Placa Vehiculo'].astype(str).str.strip().str.upper()

    # eliminar filas sin fechas válidas
    df_valid = df.dropna(subset=['Fecha_entrada_norm_full','Fecha_salida_norm_full']).copy()
    return df_valid

# -------------------------
# Buscar posibles dobles cobros
# -------------------------
def find_possible_doubles(comercio_keys, gopass_df):
    # cross join por llave (podríamos optimizar por llave_validacion igual para reducir combinaciones)
    st.write("🔍 Buscando posibles dobles cobros (aplicando tolerancia ±5 min)...")
    # Hacemos un merge por llave_validacion primero (reduce combinación)
    merged_on_key = comercio_keys.merge(gopass_df[['Transacción','Fecha_entrada_norm_full','Fecha_salida_norm_full','llave_validacion']], on='llave_validacion', how='inner', suffixes=('_comercio','_gopass'))
    if merged_on_key.empty:
        st.write("No hay coincidencias por llave (hora). Revisar tolerancias o formatos.")
        return pd.DataFrame()

    # calcular diferencias en minutos usando las fechas completas
    merged_on_key['Diferencia_entrada_min'] = (merged_on_key['Fecha_entrada'] - merged_on_key['Fecha_entrada_norm_full']).dt.total_seconds() / 60.0
    merged_on_key['Diferencia_salida_min']  = (merged_on_key['Fecha_salida'] - merged_on_key['Fecha_salida_norm_full']).dt.total_seconds() / 60.0

    # aplicar tolerancia: entrada puede ser +/-5 minutos, salida +/-5 minutos (según tu requerimiento)
    mask = merged_on_key['Diferencia_entrada_min'].between(-5, 5) & merged_on_key['Diferencia_salida_min'].between(-5, 5)
    possibles = merged_on_key[mask].copy()

    # renombrar para claridad
    if not possibles.empty:
        possibles = possibles.rename(columns={
            'Fecha_entrada': 'Comercio_entrada',
            'Fecha_salida': 'Comercio_salida',
            'Fecha_entrada_norm_full': 'Gopass_entrada',
            'Fecha_salida_norm_full': 'Gopass_salida',
            'Transacción': 'Transacción_Gopass'
        })
        possibles['llave_validacion_comercio'] = possibles['llave_validacion']
        possibles['llave_validacion_gopass'] = possibles['llave_validacion']
    return possibles

# -------------------------
# Confirmar dobles cobros
# -------------------------
def find_confirmed_doubles(possible_df, comercio_df_original, gopass_df):
    if possible_df is None or possible_df.empty:
        return pd.DataFrame()

    # Limpiar matrículas en la base original del comercio
    comercio_df_original['Matrícula_clean'] = comercio_df_original['Matrícula'].astype(str).str.strip().str.upper()
    # Filtrar matrículas válidas según tu regla (3 letras + 3 números)
    comercio_valid_plates = comercio_df_original[comercio_df_original['Matrícula_clean'].apply(plate_is_valid)][['Nº de tarjeta','Matrícula_clean']].drop_duplicates()

    # Unir posibles con las matrículas válidas por Nº de tarjeta
    merged = possible_df.merge(comercio_valid_plates, on='Nº de tarjeta', how='inner')
    if merged.empty:
        return pd.DataFrame()

    # Unir con Gopass para obtener Placa de Gopass y comparar
    gopass_plates = gopass_df[['Transacción','Placa_clean','llave_validacion']].copy()
    final = merged.merge(gopass_plates, left_on='Transacción_Gopass', right_on='Transacción', how='inner', suffixes=('','_gopass'))

    # Comparar placas
    final['coincide_placa'] = final['Matrícula_clean'] == final['Placa_clean']
    confirmed = final[final['coincide_placa']].copy()
    if confirmed.empty:
        return pd.DataFrame()

    confirmed['llave_confirmacion_comercio'] = confirmed['llave_validacion_comercio'] + "|" + confirmed['Matrícula_clean']
    confirmed['llave_confirmacion_gopass']   = confirmed['llave_validacion_gopass'] + "|" + confirmed['Placa_clean']

    select_cols = [
        'Nº de tarjeta','Transacción_Gopass','Matrícula_clean','Placa_clean',
        'Comercio_entrada','Comercio_salida','Gopass_entrada','Gopass_salida',
        'llave_confirmacion_comercio','llave_confirmacion_gopass'
    ]
    # renombrar para salida final
    out = confirmed[select_cols].rename(columns={
        'Matrícula_clean':'Matrícula_Comercio',
        'Placa_clean':'Placa_Gopass'
    })
    return out

# -------------------------
# Interfaz carga archivos
# -------------------------
st.sidebar.header("📁 Cargar Archivos")

comercio_file = st.sidebar.file_uploader("Cargar archivo del comercio (CSV o Excel)", type=['csv','xlsx','xls'], key="comercio")
gopass_file   = st.sidebar.file_uploader("Cargar archivo de Gopass (Excel)", type=['xlsx','xls'], key="gopass")

if comercio_file and gopass_file:
    try:
        with st.spinner("Cargando archivo comercio..."):
            if comercio_file.name.lower().endswith('.csv'):
                # probar distintos encodings/separadores
                try:
                    comercio_df = pd.read_csv(comercio_file, sep=';', encoding='utf-8')
                except Exception:
                    try:
                        comercio_df = pd.read_csv(comercio_file, sep=';', encoding='latin-1')
                    except Exception:
                        comercio_df = pd.read_csv(comercio_file, sep=',', encoding='utf-8', engine='python')
            else:
                comercio_df = pd.read_excel(comercio_file)

        with st.spinner("Cargando archivo Gopass..."):
            gopass_df = pd.read_excel(gopass_file)

        st.success("✅ Archivos cargados")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Base del Comercio")
            st.write(f"Filas: {len(comercio_df)} - Columnas: {len(comercio_df.columns)}")
            with st.expander("Ver columnas Comercio"):
                st.write(list(comercio_df.columns))
        with col2:
            st.subheader("Base de Gopass")
            st.write(f"Filas: {len(gopass_df)} - Columnas: {len(gopass_df.columns)}")
            with st.expander("Ver columnas Gopass"):
                st.write(list(gopass_df.columns))

        if st.button("🚀 Iniciar Validación de Dobles Cobros"):
            # procesar comercio
            comercio_filtered, comercio_keys = process_comercio_base(comercio_df)
            st.write(f"Llaves Comercio creadas: {len(comercio_keys)}")
            # procesar gopass
            gopass_processed = process_gopass_base(gopass_df)
            st.write(f"Registros Gopass válidos: {len(gopass_processed)}")
            # posibles dobles
            possible_doubles = find_possible_doubles(comercio_keys, gopass_processed)
            if possible_doubles is None or possible_doubles.empty:
                st.success("✅ No se encontraron posibles dobles cobros.")
            else:
                st.subheader("⚠️ Posibles Dobles Cobros")
                st.dataframe(possible_doubles, use_container_width=True)

                # Confirmados
                confirmed = find_confirmed_doubles(possible_doubles, comercio_df, gopass_processed)
                if confirmed is None or confirmed.empty:
                    st.info("No se encontraron dobles cobros confirmados a partir de las matrículas.")
                    # ofrecer descarga de posibles
                    csv_possible = possible_doubles.to_csv(index=False)
                    st.download_button("Descargar Posibles Dobles (CSV)", data=csv_possible, file_name="posibles_dobles.csv", mime="text/csv")
                else:
                    st.subheader("🚨 Dobles Cobros Confirmados")
                    st.dataframe(confirmed, use_container_width=True)
                    csv_confirmed = confirmed.to_csv(index=False)
                    st.download_button("Descargar Confirmados (CSV)", data=csv_confirmed, file_name="dobles_confirmados.csv", mime="text/csv")

    except Exception as e:
        st.error(f"Error al procesar los archivos: {str(e)}")
        st.write("Verifica columnas y formatos. Si el error menciona movimientos disponibles, revisa la columna 'Movimiento' en la base del comercio.")
else:
    st.info("👆 Carga ambos archivos en la barra lateral para comenzar.")
    with st.expander("Formato esperado (resumen)"):
        st.write("""
        - Base del Comercio: columnas mínimas: 'Nº de tarjeta','Tarjeta','Movimiento','Fecha/Hora','Matrícula'.
          Tarjeta debe contener 'TiqueteVehiculo' o 'Una salida 01'.
          Movimiento debe incluir 'Entrada' y 'Salida' (puede venir con variantes).
        - Base de Gopass: 'Fecha de entrada','Fecha de salida','Transacción','Placa Vehiculo'.
        - Las fechas soportadas aceptan formatos como '1/09/2025 12:03:53 a. m.' o '15/09/2025 9:37:34 p. m.'.
        """)

st.markdown("---")
st.markdown("**Desarrollado para validación de dobles cobros en sistemas de parqueaderos** 🚗")
