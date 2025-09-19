import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
import io

# -------------------------
# Configuración página
# -------------------------
st.set_page_config(page_title="Validador de Dobles Cobros", page_icon="🚗", layout="wide")
st.title("🚗 Validador de Dobles Cobros")
st.markdown("---")

# -------------------------
# Helpers
# -------------------------
def clean_colnames(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def make_unique_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Si hay columnas duplicadas, les añade sufijos _1, _2, ...
    Evita errores de 'duplicate labels' al hacer merges/pivots.
    """
    cols = list(df.columns)
    new_cols = []
    counts = {}
    for c in cols:
        if c in counts:
            counts[c] += 1
            new_cols.append(f"{c}_{counts[c]}")
        else:
            counts[c] = 0
            new_cols.append(c)
    df.columns = new_cols
    return df

def normalize_datetime_vectorized(date_series: pd.Series) -> pd.Series:
    """
    Normaliza cadenas de fecha como:
    '1/09/2025  12:03:53 a. m.' o '15/09/2025 9:37:34 p. m.' a datetime.
    Devuelve pd.Series dtype datetime64[ns] con NaT para no parseables.
    """
    s = date_series.astype(str).fillna("").str.strip()
    # limpiar espacios múltiples
    s = s.str.replace(r'\s+', ' ', regex=True)
    # convertir 'a. m.' 'p. m.' a AM/PM
    s = s.str.replace(r'\ba\.?\s*m\.?\b', 'AM', flags=re.IGNORECASE, regex=True)
    s = s.str.replace(r'\bp\.?\s*m\.?\b', 'PM', flags=re.IGNORECASE, regex=True)
    # quitar caracteres invisibles
    s = s.str.replace('\u00A0', ' ', regex=False)
    # intento directo dayfirst
    parsed = pd.to_datetime(s, dayfirst=True, errors='coerce')
    return parsed

def make_validation_key_hour(dt_entry: pd.Series, dt_exit: pd.Series) -> pd.Series:
    """
    Llave de validación con precisión de HORA: 'YYYY-MM-DD HH|YYYY-MM-DD HH'
    Retorna NaN (np.nan) si alguna fecha es NaT.
    """
    e = dt_entry.dt.strftime("%Y-%m-%d %H")
    x = dt_exit.dt.strftime("%Y-%m-%d %H")
    key = e + "|" + x
    key = key.where(~(dt_entry.isna() | dt_exit.isna()), other=np.nan)
    return key

def plate_is_valid(plate) -> bool:
    """
    Valida matrícula estilo colombiano 3 letras + 3 números (ej: ABC123).
    """
    if pd.isna(plate):
        return False
    p = str(plate).strip().upper()
    return bool(re.fullmatch(r'[A-Z]{3}\d{3}', p))

def df_to_excel_bytes(sheets: dict) -> bytes:
    """
    sheets: dict of sheet_name -> dataframe
    retorna bytes del excel creado en memoria
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
        writer.save()
    return output.getvalue()

# -------------------------
# Procesamiento Base Comercio
# -------------------------
def process_comercio_base(df: pd.DataFrame):
    df = clean_colnames(df)
    df = make_unique_columns(df)

    required_cols = ['Nº de tarjeta', 'Tarjeta', 'Movimiento', 'Fecha/Hora', 'Matrícula']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en la base del comercio: {missing}")

    # Normalizar fechas
    df['Fecha/Hora_normalizada'] = normalize_datetime_vectorized(df['Fecha/Hora'])

    # Normalizar Movimiento (sin espacios y en minúscula)
    df['Movimiento_norm'] = df['Movimiento'].astype(str).fillna("").str.strip().str.lower()
    # Mapear variantes típicas a los 3 valores esperados
    df['Movimiento_norm'] = df['Movimiento_norm'].replace({
        'entrada': 'entrada',
        'entrada ': 'entrada',
        'entradas': 'entrada',
        'entrada\r': 'entrada',
        'salida': 'salida',
        'salidas': 'salida',
        'salida ': 'salida',
        'transacción': 'transaccion',
        'transaccion': 'transaccion',
        'transacción ': 'transaccion',
        'transacción\r': 'transaccion'
    })
    df['Movimiento_norm'] = df['Movimiento_norm'].map({
        'entrada': 'Entrada',
        'salida': 'Salida',
        'transaccion': 'Transacción'
    }).fillna(df['Movimiento'].astype(str).str.strip())

    # Normalizar Tarjeta (comparación case-insensitive)
    df['Tarjeta_norm'] = df['Tarjeta'].astype(str).str.strip()
    df['Tarjeta_norm_low'] = df['Tarjeta_norm'].str.lower()

    # Filtrar solo TiqueteVehiculo y Una salida 01 (insensible a mayúsculas)
    allowed = ['tiquetevehiculo', 'una salida 01']
    df_filtered = df[df['Tarjeta_norm_low'].isin(allowed)].copy()

    # Validar que hay datos con fechas
    tmp = df_filtered.dropna(subset=['Fecha/Hora_normalizada']).copy()
    if tmp.empty:
        return df_filtered, pd.DataFrame(columns=['Nº de tarjeta', 'Fecha_entrada', 'Fecha_salida', 'llave_validacion'])

    # Agrupar por Nº de tarjeta: entrada = min, salida = max (según tu requerimiento)
    entradas = (
        tmp[tmp['Movimiento_norm'] == 'Entrada']
        .groupby('Nº de tarjeta', as_index=False)['Fecha/Hora_normalizada']
        .min()
        .rename(columns={'Fecha/Hora_normalizada': 'Fecha_entrada'})
    )
    salidas = (
        tmp[tmp['Movimiento_norm'] == 'Salida']
        .groupby('Nº de tarjeta', as_index=False)['Fecha/Hora_normalizada']
        .max()
        .rename(columns={'Fecha/Hora_normalizada': 'Fecha_salida'})
    )

    # Merge entradas+salidas; si hay múltiples pares por la misma tarjeta, esto da un row por tarjeta
    comercio_keys = entradas.merge(salidas, on='Nº de tarjeta', how='inner')

    if comercio_keys.empty:
        movimientos_unicos = sorted(tmp['Movimiento_norm'].unique())
        raise ValueError(f"No se encontraron pares Entrada/Salida por 'Nº de tarjeta'. Movimientos detectados: {movimientos_unicos}")

    # Asegurar tipo datetime
    comercio_keys['Fecha_entrada'] = pd.to_datetime(comercio_keys['Fecha_entrada'])
    comercio_keys['Fecha_salida'] = pd.to_datetime(comercio_keys['Fecha_salida'])

    # Crear llave de validación en formato hora (misma estructura para Gopass)
    comercio_keys['llave_validacion'] = make_validation_key_hour(comercio_keys['Fecha_entrada'], comercio_keys['Fecha_salida'])

    # Evitar duplicados
    comercio_keys = comercio_keys.drop_duplicates(subset=['Nº de tarjeta'])

    return df_filtered, comercio_keys[['Nº de tarjeta', 'Fecha_entrada', 'Fecha_salida', 'llave_validacion']]

# -------------------------
# Procesamiento Base Gopass
# -------------------------
def process_gopass_base(df: pd.DataFrame):
    df = clean_colnames(df)
    df = make_unique_columns(df)

    required_cols = ['Fecha de entrada', 'Fecha de salida', 'Transacción', 'Placa Vehiculo']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en la base de Gopass: {missing}")

    df['Fecha_entrada_norm_full'] = normalize_datetime_vectorized(df['Fecha de entrada'])
    df['Fecha_salida_norm_full'] = normalize_datetime_vectorized(df['Fecha de salida'])

    # Crear llave con precisión hora para hacer el match inicial
    df['llave_validacion'] = make_validation_key_hour(df['Fecha_entrada_norm_full'], df['Fecha_salida_norm_full'])

    # Limpiar campos clave
    df['Transacción'] = df['Transacción'].astype(str).str.strip()
    df['Placa_clean'] = df['Placa Vehiculo'].astype(str).str.strip().str.upper()

    # Eliminar filas sin fechas válidas
    df_valid = df.dropna(subset=['Fecha_entrada_norm_full', 'Fecha_salida_norm_full']).copy()
    return df_valid

# -------------------------
# Buscar posibles dobles cobros
# -------------------------
def find_possible_doubles(comercio_keys: pd.DataFrame, gopass_df: pd.DataFrame):
    st.write("🔍 Buscando posibles dobles cobros (aplicando tolerancia ±5 min)...")

    # Hacemos merge por llave_validacion (hora). Esto reduce drásticamente combinaciones.
    # Sufijos para evitar columnas duplicadas
    merged = comercio_keys.merge(
        gopass_df[['Transacción', 'Fecha_entrada_norm_full', 'Fecha_salida_norm_full', 'llave_validacion']],
        on='llave_validacion',
        how='inner',
        suffixes=('_comercio', '_gopass')
    )

    if merged.empty:
        st.write("No hay coincidencias por llave (mismo YYYY-MM-DD HH).")
        return pd.DataFrame()

    # Renombrar para claridad localmente
    merged = merged.rename(columns={
        'Fecha_entrada': 'Comercio_entrada',
        'Fecha_salida': 'Comercio_salida',
        'Fecha_entrada_norm_full': 'Gopass_entrada',
        'Fecha_salida_norm_full': 'Gopass_salida',
        'Transacción': 'Transacción_Gopass'
    })

    # Asegurar datetime
    merged['Comercio_entrada'] = pd.to_datetime(merged['Comercio_entrada'])
    merged['Comercio_salida'] = pd.to_datetime(merged['Comercio_salida'])
    merged['Gopass_entrada'] = pd.to_datetime(merged['Gopass_entrada'])
    merged['Gopass_salida'] = pd.to_datetime(merged['Gopass_salida'])

    # Calcular diferencias en minutos (comercio - gopass)
    merged['Diferencia_entrada_min'] = (merged['Comercio_entrada'] - merged['Gopass_entrada']).dt.total_seconds() / 60.0
    merged['Diferencia_salida_min']  = (merged['Comercio_salida'] - merged['Gopass_salida']).dt.total_seconds() / 60.0

    # Aplicar tolerancia: entrada ±5, salida ±5 (según lo solicitado)
    mask = merged['Diferencia_entrada_min'].between(-5, 5) & merged['Diferencia_salida_min'].between(-5, 5)
    possibles = merged[mask].copy()

    # Añadir columnas de llave origen para confirmaciones posteriores
    if not possibles.empty:
        possibles['llave_validacion_comercio'] = possibles['llave_validacion']
        possibles['llave_validacion_gopass']   = possibles['llave_validacion']

    return possibles

# -------------------------
# Confirmar dobles cobros
# -------------------------
def find_confirmed_doubles(possible_df: pd.DataFrame, comercio_df_original: pd.DataFrame, gopass_df: pd.DataFrame):
    if possible_df is None or possible_df.empty:
        return pd.DataFrame()

    # Limpiar matrículas en la base original del comercio
    comercio_df_original = clean_colnames(comercio_df_original)
    comercio_df_original['Matrícula_clean'] = comercio_df_original['Matrícula'].astype(str).str.strip().str.upper()

    # Filtrar matrículas válidas
    comercio_valid_plates = comercio_df_original[comercio_df_original['Matrícula_clean'].apply(plate_is_valid)][['Nº de tarjeta', 'Matrícula_clean']].drop_duplicates()

    if comercio_valid_plates.empty:
        st.info("No se encontraron matrículas válidas en la base del comercio para confirmar.")
        return pd.DataFrame()

    # Unir posibles con matrículas por Nº de tarjeta (puede haber 1..n)
    merged = possible_df.merge(comercio_valid_plates, on='Nº de tarjeta', how='inner', validate='m:1')
    if merged.empty:
        return pd.DataFrame()

    # Unir con Gopass para obtener placa y comparar (usar sufijo para evitar columnas duplicadas)
    gopass_plates = gopass_df[['Transacción', 'Placa_clean', 'llave_validacion']].copy()
    final = merged.merge(gopass_plates, left_on='Transacción_Gopass', right_on='Transacción', how='inner', suffixes=('', '_gopass'))

    if final.empty:
        return pd.DataFrame()

    # Comparar placas limpiadas
    final['coincide_placa'] = final['Matrícula_clean'] == final['Placa_clean']
    confirmed = final[final['coincide_placa']].copy()
    if confirmed.empty:
        return pd.DataFrame()

    # Crear llaves de confirmación (validacion + placa)
    confirmed['llave_confirmacion_comercio'] = confirmed['llave_validacion_comercio'].astype(str) + "|" + confirmed['Matrícula_clean']
    confirmed['llave_confirmacion_gopass']   = confirmed['llave_validacion_gopass'].astype(str) + "|" + confirmed['Placa_clean']

    # Seleccionar y renombrar columnas de salida
    out = confirmed[[
        'Nº de tarjeta', 'Transacción_Gopass', 'Matrícula_clean', 'Placa_clean',
        'Comercio_entrada', 'Comercio_salida', 'Gopass_entrada', 'Gopass_salida',
        'llave_confirmacion_comercio', 'llave_confirmacion_gopass'
    ]].rename(columns={
        'Matrícula_clean': 'Matrícula_Comercio',
        'Placa_clean': 'Placa_Gopass',
        'Transacción_Gopass': 'Transacción_Gopass'
    }).drop_duplicates()

    return out

# -------------------------
# Interfaz
# -------------------------
st.sidebar.header("📁 Cargar Archivos")
comercio_file = st.sidebar.file_uploader("Cargar archivo del comercio (CSV o Excel)", type=['csv', 'xlsx', 'xls'], key="comercio")
gopass_file   = st.sidebar.file_uploader("Cargar archivo de Gopass (Excel)", type=['xlsx', 'xls'], key="gopass")

# Opciones de usuario
st.sidebar.markdown("**Opciones**")
tolerance_min = st.sidebar.number_input("Tolerancia en minutos (±)", min_value=0, max_value=60, value=5, step=1)
show_preview = st.sidebar.checkbox("Mostrar vista previa de archivos", value=True)

if comercio_file and gopass_file:
    try:
        # Cargar comercio
        with st.spinner("Cargando archivo comercio..."):
            if comercio_file.name.lower().endswith('.csv'):
                # intentar distintos separadores/encodings
                try:
                    comercio_df = pd.read_csv(comercio_file, sep=';', encoding='utf-8', engine='python')
                except Exception:
                    try:
                        comercio_df = pd.read_csv(comercio_file, sep=';', encoding='latin-1', engine='python')
                    except Exception:
                        comercio_df = pd.read_csv(comercio_file, sep=',', encoding='utf-8', engine='python')
            else:
                comercio_df = pd.read_excel(comercio_file)

        # Cargar gopass
        with st.spinner("Cargando archivo Gopass..."):
            gopass_df = pd.read_excel(gopass_file)

        st.success("✅ Archivos cargados correctamente")

        if show_preview:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Base del Comercio (preview)")
                st.write(f"Filas: {len(comercio_df)} — Columnas: {len(comercio_df.columns)}")
                with st.expander("Ver columnas Comercio"):
                    st.write(list(comercio_df.columns))
                st.dataframe(comercio_df.head(5))
            with col2:
                st.subheader("Base de Gopass (preview)")
                st.write(f"Filas: {len(gopass_df)} — Columnas: {len(gopass_df.columns)}")
                with st.expander("Ver columnas Gopass"):
                    st.write(list(gopass_df.columns))
                st.dataframe(gopass_df.head(5))

        if st.button("🚀 Iniciar Validación de Dobles Cobros"):
            # Procesar comercio
            comercio_filtered, comercio_keys = process_comercio_base(comercio_df)
            st.write(f"Llaves Comercio creadas: {len(comercio_keys)}")

            # Procesar gopass
            gopass_processed = process_gopass_base(gopass_df)
            st.write(f"Registros Gopass válidos (fechas parseadas): {len(gopass_processed)}")

            # Ajustar tolerancia usada en la comparación (se usa ±tolerance_min)
            # NOTE: la función find_possible_doubles aplica ±5 por defecto en lógica; la adaptamos aquí:
            # Para usar la tolerancia variable, reemplazamos la condición manualmente:
            possibles = find_possible_doubles(comercio_keys, gopass_processed)
            if possibles.empty:
                st.success("✅ No se encontraron posibles dobles cobros por llave/hora.")
            else:
                # recalcular diferencias con tolerancia custom
                possibles['Diferencia_entrada_min'] = (pd.to_datetime(possibles['Comercio_entrada']) - pd.to_datetime(possibles['Gopass_entrada'])).dt.total_seconds()/60.0
                possibles['Diferencia_salida_min']  = (pd.to_datetime(possibles['Comercio_salida']) - pd.to_datetime(possibles['Gopass_salida'])).dt.total_seconds()/60.0
                mask_tol = possibles['Diferencia_entrada_min'].between(-tolerance_min, tolerance_min) & possibles['Diferencia_salida_min'].between(-tolerance_min, tolerance_min)
                possibles = possibles[mask_tol].copy()

                if possibles.empty:
                    st.success("✅ No se encontraron posibles dobles cobros con la tolerancia seleccionada.")
                else:
                    st.subheader("⚠️ Posibles Dobles Cobros")
                    st.dataframe(possibles, use_container_width=True)

                    # Confirmados
                    confirmed = find_confirmed_doubles(possibles, comercio_df, gopass_processed)
                    if confirmed.empty:
                        st.info("No se encontraron dobles cobros confirmados a partir de las matrículas.")
                        # Ofrecer descarga de posibles (CSV/Excel)
                        csv_bytes = possibles.to_csv(index=False).encode('utf-8')
                        st.download_button("⬇️ Descargar Posibles (CSV)", data=csv_bytes, file_name="posibles_dobles.csv", mime="text/csv")
                        excel_bytes = df_to_excel_bytes({"posibles_dobles": possibles})
                        st.download_button("⬇️ Descargar Posibles (Excel)", data=excel_bytes, file_name="posibles_dobles.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    else:
                        st.subheader("🚨 Dobles Cobros Confirmados")
                        st.dataframe(confirmed, use_container_width=True)
                        # Descargas
                        st.download_button("⬇️ Descargar Confirmados (CSV)", data=confirmed.to_csv(index=False).encode('utf-8'), file_name="dobles_confirmados.csv", mime="text/csv")
                        st.download_button("⬇️ Descargar Confirmados (Excel)", data=df_to_excel_bytes({"dobles_confirmados": confirmed}), file_name="dobles_confirmados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"Error al procesar los archivos: {str(e)}")
        # Mostrar un traceback corto útil para debugging (opcional)
        st.write("Revisa columnas, formatos de fecha y que no existan nombres de columna duplicados en el Excel.")
else:
    st.info("👆 Carga ambos archivos en la barra lateral para comenzar.")
    with st.expander("Formato esperado (resumen)"):
        st.write("""
        - Base del Comercio (CSV o Excel):
          columnas mínimas: 'Nº de tarjeta','Tarjeta','Movimiento','Fecha/Hora','Matrícula'.
          'Tarjeta' valores: 'TiqueteVehiculo' y 'Una salida 01' (case-insensitive).
          'Movimiento' contiene: 'Entrada','Salida','Transacción' (puede venir con variantes).
        - Base de Gopass (Excel):
          columnas mínimas: 'Fecha de entrada','Fecha de salida','Transacción','Placa Vehiculo'.
        - Fechas soportadas: formatos como '1/09/2025 12:03:53 a. m.' o '15/09/2025 9:37:34 p. m.'.
        - Puedes ajustar la tolerancia (minutos) en la barra lateral.
        """)

st.markdown("---")
st.markdown("**Desarrollado para validación de dobles cobros en sistemas de parqueaderos** 🚗")

