import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
import io

# Configuración de la página
st.set_page_config(
    page_title="Validador de Dobles Cobros",
    page_icon="🚗",
    layout="wide"
)

st.title("🚗 Validador de Dobles Cobros")
st.markdown("---")

def normalize_datetime_vectorized(date_series):
    """
    Normaliza fechas de forma vectorizada usando pandas
    """
    # Convertir a string y limpiar
    date_series = date_series.astype(str).str.strip()
    date_series = date_series.str.replace(r'\s+', ' ', regex=True)
    
    # Intentar conversión directa con pandas (más rápido)
    try:
        return pd.to_datetime(date_series, format='%d/%m/%Y %H:%M:%S', errors='coerce')
    except:
        pass
    
    # Si falla, usar regex para casos específicos
    def parse_single_date(date_str):
        if pd.isna(date_str) or date_str == 'nan':
            return None
        
        patterns = [
            r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(a\.|p\.)\s*m\.',
            r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)',
            r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, str(date_str), re.IGNORECASE)
            if match:
                day, month, year, hour, minute, second = match.groups()[:6]
                
                if len(match.groups()) > 6 and match.groups()[6]:
                    am_pm = match.groups()[6].lower()
                    hour = int(hour)
                    if 'p' in am_pm and hour != 12:
                        hour += 12
                    elif 'a' in am_pm and hour == 12:
                        hour = 0
                
                try:
                    return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
                except ValueError:
                    continue
        
        try:
            return pd.to_datetime(str(date_str))
        except:
            return None
    
    return date_series.apply(parse_single_date)

def create_validation_key_vectorized(entry_dates, exit_dates):
    """
    Crea llaves de validación de forma vectorizada
    """
    entry_str = entry_dates.dt.strftime("%d/%m/%Y %H")
    exit_str = exit_dates.dt.strftime("%d/%m/%Y %H")
    return entry_str + "|" + exit_str

def process_comercio_base_optimized(df):
    """
    Procesa la base del comercio de forma optimizada
    """
    st.write("### Procesando Base del Comercio...")
    st.write(f"Registros iniciales: {len(df)}")
    
    # Normalizar fecha/hora vectorizada
    st.write("📅 Normalizando formato de Fecha/Hora...")
    with st.spinner("Procesando fechas..."):
        df['Fecha/Hora_normalizada'] = normalize_datetime_vectorized(df['Fecha/Hora'])
    
    # Filtrar por tarjeta
    st.write("🎫 Filtrando por tipo de tarjeta...")
    df_filtered = df[df['Tarjeta'].isin(['TiqueteVehiculo', 'Una salida 01'])].copy()
    st.write(f"Registros después del filtro: {len(df_filtered)}")
    
    # Crear llaves de validación usando groupby (más eficiente)
    st.write("🔑 Creando llaves de validación...")
    with st.spinner("Agrupando por número de tarjeta..."):
        # Pivot para obtener entrada y salida por tarjeta
        pivot_data = df_filtered.pivot_table(
            index='Nº de tarjeta',
            columns='Movimiento',
            values='Fecha/Hora_normalizada',
            aggfunc='first'
        ).reset_index()
        
        # Filtrar solo los que tienen entrada y salida
        valid_cards = pivot_data.dropna(subset=['Entrada', 'Salida'])
        
        # Crear llaves vectorizadas
        valid_cards['llave_validacion'] = create_validation_key_vectorized(
            valid_cards['Entrada'], 
            valid_cards['Salida']
        )
        
        # Preparar resultado
        comercio_keys_df = valid_cards[['Nº de tarjeta', 'Entrada', 'Salida', 'llave_validacion']].copy()
        comercio_keys_df.columns = ['Nº de tarjeta', 'Fecha_entrada', 'Fecha_salida', 'llave_validacion']
    
    st.write(f"Llaves de validación creadas: {len(comercio_keys_df)}")
    return df_filtered, comercio_keys_df

def process_gopass_base_optimized(df):
    """
    Procesa la base de Gopass de forma optimizada
    """
    st.write("### Procesando Base de Gopass...")
    st.write(f"Registros iniciales: {len(df)}")
    
    # Normalizar fechas vectorizadas
    st.write("📅 Normalizando fechas de entrada y salida...")
    with st.spinner("Procesando fechas..."):
        df['Fecha_entrada_norm'] = normalize_datetime_vectorized(df['Fecha de entrada'])
        df['Fecha_salida_norm'] = normalize_datetime_vectorized(df['Fecha de salida'])
    
    # Crear llaves de validación vectorizadas
    st.write("🔑 Creando llaves de validación...")
    df['llave_validacion'] = create_validation_key_vectorized(
        df['Fecha_entrada_norm'], 
        df['Fecha_salida_norm']
    )
    
    # Remover registros sin llave válida
    df_valid = df.dropna(subset=['llave_validacion']).copy()
    st.write(f"Registros con llave válida: {len(df_valid)}")
    
    return df_valid

def find_possible_double_billing_optimized(comercio_keys, gopass_df):
    """
    Encuentra posibles dobles cobros de forma súper optimizada usando cross join
    """
    st.write("### 🔍 Buscando Posibles Dobles Cobros...")
    
    with st.spinner("Comparando registros..."):
        # Cross join usando merge con key dummy
        comercio_keys['_merge_key'] = 1
        gopass_df['_merge_key'] = 1
        
        cross_joined = comercio_keys.merge(
            gopass_df[['Transacción', 'Fecha_entrada_norm', 'Fecha_salida_norm', 'llave_validacion', '_merge_key']],
            on='_merge_key',
            suffixes=('_comercio', '_gopass')
        ).drop('_merge_key', axis=1)
        
        # Calcular diferencias en minutos de forma vectorizada
        cross_joined['Diferencia_entrada_min'] = (
            cross_joined['Fecha_entrada'] - cross_joined['Fecha_entrada_norm']
        ).dt.total_seconds() / 60
        
        cross_joined['Diferencia_salida_min'] = (
            cross_joined['Fecha_salida_norm'] - cross_joined['Fecha_salida']
        ).dt.total_seconds() / 60
        
        # Filtrar con tolerancia de ±5 minutos
        mask = (
            cross_joined['Diferencia_entrada_min'].between(-5, 5) &
            cross_joined['Diferencia_salida_min'].between(-5, 5)
        )
        
        possible_doubles_df = cross_joined[mask].copy()
        
        # Renombrar columnas para claridad
        possible_doubles_df = possible_doubles_df.rename(columns={
            'Transacción': 'Transacción_Gopass',
            'Fecha_entrada': 'Comercio_entrada',
            'Fecha_salida': 'Comercio_salida',
            'Fecha_entrada_norm': 'Gopass_entrada',
            'Fecha_salida_norm': 'Gopass_salida',
            'llave_validacion_comercio': 'llave_validacion_comercio',
            'llave_validacion_gopass': 'llave_validacion_gopass'
        })
    
    st.write(f"Posibles dobles cobros encontrados: {len(possible_doubles_df)}")
    return possible_doubles_df

def find_confirmed_double_billing_optimized(possible_doubles_df, comercio_df_original, gopass_df):
    """
    Confirma dobles cobros de forma optimizada usando merges
    """
    st.write("### ✅ Confirmando Dobles Cobros...")
    
    if len(possible_doubles_df) == 0:
        return pd.DataFrame()
    
    with st.spinner("Validando matrículas..."):
        # Preparar datos de matrículas válidas
        comercio_df_original['Matrícula_clean'] = (
            comercio_df_original['Matrícula']
            .astype(str)
            .str.strip()
            .str.upper()
        )
        
        # Filtrar matrículas válidas usando regex vectorizada
        valid_plates_mask = comercio_df_original['Matrícula_clean'].str.match(r'^[A-Z]{3}\d{3}$', na=False)
        comercio_plates = comercio_df_original[valid_plates_mask][['Nº de tarjeta', 'Matrícula_clean']].drop_duplicates()
        
        # Merge con posibles dobles cobros
        merged_with_plates = possible_doubles_df.merge(
            comercio_plates,
            on='Nº de tarjeta',
            how='inner'
        )
        
        # Preparar datos de Gopass
        gopass_plates = gopass_df[['Transacción', 'Placa Vehiculo']].copy()
        gopass_plates['Placa_clean'] = (
            gopass_plates['Placa Vehiculo']
            .astype(str)
            .str.strip()
            .str.upper()
        )
        
        # Merge con datos de Gopass
        final_merged = merged_with_plates.merge(
            gopass_plates,
            left_on='Transacción_Gopass',
            right_on='Transacción',
            how='inner'
        )
        
        # Filtrar donde las placas coinciden
        confirmed_doubles_df = final_merged[
            final_merged['Matrícula_clean'] == final_merged['Placa_clean']
        ].copy()
        
        # Crear llaves de confirmación
        if len(confirmed_doubles_df) > 0:
            confirmed_doubles_df['llave_confirmacion_comercio'] = (
                confirmed_doubles_df['llave_validacion_comercio'] + "|" + 
                confirmed_doubles_df['Matrícula_clean']
            )
            confirmed_doubles_df['llave_confirmacion_gopass'] = (
                confirmed_doubles_df['llave_validacion_gopass'] + "|" + 
                confirmed_doubles_df['Placa_clean']
            )
            
            # Seleccionar columnas finales
            result_cols = [
                'Nº de tarjeta', 'Transacción_Gopass', 'Matrícula_clean', 'Placa_clean',
                'Comercio_entrada', 'Comercio_salida', 'Gopass_entrada', 'Gopass_salida',
                'llave_confirmacion_comercio', 'llave_confirmacion_gopass'
            ]
            confirmed_doubles_df = confirmed_doubles_df[result_cols].rename(columns={
                'Matrícula_clean': 'Matrícula_Comercio',
                'Placa_clean': 'Placa_Gopass'
            })
    
    st.write(f"Dobles cobros confirmados: {len(confirmed_doubles_df)}")
    return confirmed_doubles_df

# Interfaz de usuario
st.sidebar.header("📁 Cargar Archivos")

# Cargar base del comercio
st.sidebar.subheader("Base del Comercio")
comercio_file = st.sidebar.file_uploader(
    "Cargar archivo del comercio (CSV o Excel)",
    type=['csv', 'xlsx', 'xls'],
    key="comercio"
)

# Cargar base de Gopass
st.sidebar.subheader("Base de Gopass")
gopass_file = st.sidebar.file_uploader(
    "Cargar archivo de Gopass (Excel)",
    type=['xlsx', 'xls'],
    key="gopass"
)

if comercio_file and gopass_file:
    try:
        # Leer base del comercio
        with st.spinner("Cargando base del comercio..."):
            if comercio_file.name.endswith('.csv'):
                # Intentar con diferentes separadores
                try:
                    comercio_df = pd.read_csv(comercio_file, sep=';', encoding='utf-8')
                    st.info("Archivo CSV cargado con separador ';'")
                except:
                    try:
                        comercio_df = pd.read_csv(comercio_file, sep=';', encoding='latin-1')
                        st.info("Archivo CSV cargado con separador ';' y encoding latin-1")
                    except:
                        comercio_df = pd.read_csv(comercio_file, sep=',')
                        st.info("Archivo CSV cargado con separador ','")
            else:
                comercio_df = pd.read_excel(comercio_file)
        
        # Leer base de Gopass
        with st.spinner("Cargando base de Gopass..."):
            gopass_df = pd.read_excel(gopass_file)
        
        st.success("✅ Ambos archivos cargados correctamente!")
        
        # Verificar que las columnas esperadas estén presentes
        expected_comercio_cols = ['Nº de tarjeta', 'Tarjeta', 'Movimiento', 'Fecha/Hora', 'Matrícula']
        missing_comercio_cols = [col for col in expected_comercio_cols if col not in comercio_df.columns]
        
        if missing_comercio_cols:
            st.error(f"❌ Faltan columnas en la base del comercio: {missing_comercio_cols}")
            st.write("Columnas disponibles:", list(comercio_df.columns))
            st.stop()
        
        expected_gopass_cols = ['Fecha de entrada', 'Fecha de salida', 'Transacción', 'Placa Vehiculo']
        missing_gopass_cols = [col for col in expected_gopass_cols if col not in gopass_df.columns]
        
        if missing_gopass_cols:
            st.error(f"❌ Faltan columnas en la base de Gopass: {missing_gopass_cols}")
            st.write("Columnas disponibles:", list(gopass_df.columns))
            st.stop()
        
        # Mostrar información de los archivos
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Base del Comercio")
            st.write(f"Filas: {len(comercio_df)}")
            st.write(f"Columnas: {len(comercio_df.columns)}")
            with st.expander("Ver columnas"):
                st.write(list(comercio_df.columns))
        
        with col2:
            st.subheader("📊 Base de Gopass")
            st.write(f"Filas: {len(gopass_df)}")
            st.write(f"Columnas: {len(gopass_df.columns)}")
            with st.expander("Ver columnas"):
                st.write(list(gopass_df.columns))
        
        # Botón para iniciar validación
        if st.button("🚀 Iniciar Validación de Dobles Cobros", type="primary"):
            
            # Procesar base del comercio
            comercio_filtered, comercio_keys = process_comercio_base_optimized(comercio_df)
            
            # Procesar base de Gopass
            gopass_processed = process_gopass_base_optimized(gopass_df)
            
            # Buscar posibles dobles cobros
            possible_doubles = find_possible_double_billing_optimized(comercio_keys, gopass_processed)
            
            if len(possible_doubles) > 0:
                # Mostrar posibles dobles cobros
                st.subheader("⚠️ Posibles Dobles Cobros")
                st.dataframe(possible_doubles, use_container_width=True)
                
                # Buscar dobles cobros confirmados
                confirmed_doubles = find_confirmed_double_billing_optimized(
                    possible_doubles, comercio_df, gopass_processed
                )
                
                if len(confirmed_doubles) > 0:
                    st.subheader("🚨 Dobles Cobros Confirmados")
                    st.dataframe(confirmed_doubles, use_container_width=True)
                    
                    # Opción para descargar resultados
                    st.subheader("💾 Descargar Resultados")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Descargar posibles dobles cobros
                        csv_possible = possible_doubles.to_csv(index=False)
                        st.download_button(
                            label="📄 Descargar Posibles Dobles Cobros (CSV)",
                            data=csv_possible,
                            file_name=f"posibles_dobles_cobros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    
                    with col2:
                        # Descargar dobles cobros confirmados
                        csv_confirmed = confirmed_doubles.to_csv(index=False)
                        st.download_button(
                            label="📄 Descargar Dobles Cobros Confirmados (CSV)",
                            data=csv_confirmed,
                            file_name=f"dobles_cobros_confirmados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                
                else:
                    st.success("✅ No se encontraron dobles cobros confirmados.")
                    
                    # Mostrar solo posibles dobles cobros para descarga
                    csv_possible = possible_doubles.to_csv(index=False)
                    st.download_button(
                        label="📄 Descargar Posibles Dobles Cobros (CSV)",
                        data=csv_possible,
                        file_name=f"posibles_dobles_cobros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
            else:
                st.success("✅ No se encontraron dobles cobros.")
                
    except Exception as e:
        st.error(f"Error al procesar los archivos: {str(e)}")
        st.write("Por favor, verifica que los archivos tengan el formato correcto.")

else:
    st.info("👆 Por favor, carga ambos archivos en la barra lateral para comenzar la validación.")
    
    # Información sobre el formato esperado
    with st.expander("📋 Información sobre el formato de archivos"):
        st.write("""
        **Base del Comercio:**
        - Formato: CSV o Excel
        - Columnas esperadas: Nº de tarjeta, Importe, Valor restante, Valor, Tarjeta, Aparcamiento, Garaje, Equipo, Rechazo, Observación, Matrícula, Fecha/Hora, Movimiento
        - La columna 'Tarjeta' debe contener valores 'TiqueteVehiculo' y 'Una salida 01'
        - La columna 'Movimiento' debe contener 'Entrada', 'Salida', 'Transacción'
        
        **Base de Gopass:**
        - Formato: Excel
        - Debe contener las columnas: 'Fecha de entrada', 'Fecha de salida', 'Transacción', 'Placa Vehiculo'
        
        **Formato de fechas soportado:**
        - DD/MM/YYYY HH:MM:SS a.m./p.m.
        - DD/MM/YYYY HH:MM:SS AM/PM
        """)

# Footer
st.markdown("---")
st.markdown("**Desarrollado para validación de dobles cobros en sistemas de parqueaderos** 🚗")
