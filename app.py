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

def normalize_datetime(date_str):
    """
    Normaliza diferentes formatos de fecha/hora a un formato estándar
    """
    if pd.isna(date_str):
        return None
    
    # Convertir a string si no lo es
    date_str = str(date_str)
    
    # Remover espacios extra y convertir a minúsculas para a.m./p.m.
    date_str = re.sub(r'\s+', ' ', date_str.strip())
    
    # Patrones comunes de fecha
    patterns = [
        r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(a\.|p\.)\s*m\.',
        r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)',
        r'(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})',
        r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, date_str, re.IGNORECASE)
        if match:
            if len(match.groups()) >= 6:
                if pattern == patterns[3]:  # Formato YYYY-MM-DD
                    year, month, day, hour, minute, second = match.groups()[:6]
                else:  # Formato DD/MM/YYYY
                    day, month, year, hour, minute, second = match.groups()[:6]
                
                # Manejar AM/PM si existe
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
    
    # Si no coincide con ningún patrón, intentar con pandas
    try:
        return pd.to_datetime(date_str)
    except:
        return None

def create_validation_key(entry_date, exit_date):
    """
    Crea una llave de validación con fecha de entrada y salida (sin minutos ni segundos)
    """
    if pd.isna(entry_date) or pd.isna(exit_date):
        return None
    
    # Formatear sin minutos ni segundos
    entry_str = entry_date.strftime("%d/%m/%Y %H")
    exit_str = exit_date.strftime("%d/%m/%Y %H")
    
    return f"{entry_str}|{exit_str}"

def is_valid_license_plate(plate):
    """
    Valida si una matrícula cumple el formato: 3 letras + 3 números
    """
    if pd.isna(plate):
        return False
    
    plate_str = str(plate).strip().upper()
    pattern = r'^[A-Z]{3}\d{3}$'
    return bool(re.match(pattern, plate_str)) and len(plate_str) == 6

def process_comercio_base(df):
    """
    Procesa la base del comercio
    """
    st.write("### Procesando Base del Comercio...")
    
    # Mostrar información inicial
    st.write(f"Registros iniciales: {len(df)}")
    
    # Normalizar fecha/hora
    st.write("📅 Normalizando formato de Fecha/Hora...")
    df['Fecha/Hora_normalizada'] = df['Fecha/Hora'].apply(normalize_datetime)
    
    # Filtrar por tarjeta
    st.write("🎫 Filtrando por tipo de tarjeta...")
    df_filtered = df[df['Tarjeta'].isin(['TiqueteVehiculo', 'Una salida 01'])].copy()
    st.write(f"Registros después del filtro: {len(df_filtered)}")
    
    # Crear llaves de validación por Nº de tarjeta
    st.write("🔑 Creando llaves de validación...")
    
    validation_keys = []
    card_numbers = df_filtered['Nº de tarjeta'].unique()
    
    progress_bar = st.progress(0)
    total_cards = len(card_numbers)
    
    for i, card_num in enumerate(card_numbers):
        card_records = df_filtered[df_filtered['Nº de tarjeta'] == card_num]
        
        # Buscar entrada y salida
        entrada = card_records[card_records['Movimiento'] == 'Entrada']
        salida = card_records[card_records['Movimiento'] == 'Salida']
        
        if not entrada.empty and not salida.empty:
            entry_date = entrada['Fecha/Hora_normalizada'].iloc[0]
            exit_date = salida['Fecha/Hora_normalizada'].iloc[0]
            
            validation_key = create_validation_key(entry_date, exit_date)
            if validation_key:
                validation_keys.append({
                    'Nº de tarjeta': card_num,
                    'Fecha_entrada': entry_date,
                    'Fecha_salida': exit_date,
                    'llave_validacion': validation_key
                })
        
        progress_bar.progress((i + 1) / total_cards)
    
    comercio_keys_df = pd.DataFrame(validation_keys)
    st.write(f"Llaves de validación creadas: {len(comercio_keys_df)}")
    
    return df_filtered, comercio_keys_df

def process_gopass_base(df):
    """
    Procesa la base de Gopass
    """
    st.write("### Procesando Base de Gopass...")
    
    st.write(f"Registros iniciales: {len(df)}")
    
    # Normalizar fechas
    st.write("📅 Normalizando fechas de entrada y salida...")
    df['Fecha_entrada_norm'] = df['Fecha de entrada'].apply(normalize_datetime)
    df['Fecha_salida_norm'] = df['Fecha de salida'].apply(normalize_datetime)
    
    # Crear llaves de validación
    st.write("🔑 Creando llaves de validación...")
    df['llave_validacion'] = df.apply(
        lambda row: create_validation_key(row['Fecha_entrada_norm'], row['Fecha_salida_norm']), 
        axis=1
    )
    
    # Remover registros sin llave válida
    df_valid = df.dropna(subset=['llave_validacion']).copy()
    st.write(f"Registros con llave válida: {len(df_valid)}")
    
    return df_valid

def find_possible_double_billing(comercio_keys, gopass_df):
    """
    Encuentra posibles dobles cobros con tolerancia de 5 minutos
    """
    st.write("### 🔍 Buscando Posibles Dobles Cobros...")
    
    possible_doubles = []
    
    progress_bar = st.progress(0)
    total_comercio = len(comercio_keys)
    
    for i, comercio_row in comercio_keys.iterrows():
        comercio_entry = comercio_row['Fecha_entrada']
        comercio_exit = comercio_row['Fecha_salida']
        
        for j, gopass_row in gopass_df.iterrows():
            gopass_entry = gopass_row['Fecha_entrada_norm']
            gopass_exit = gopass_row['Fecha_salida_norm']
            
            # Tolerancia de 5 minutos
            # Entrada del comercio puede ser hasta 5 min mayor que Gopass
            entry_diff = (comercio_entry - gopass_entry).total_seconds() / 60
            # Salida del comercio puede ser hasta 5 min menor que Gopass
            exit_diff = (gopass_exit - comercio_exit).total_seconds() / 60
            
            if -5 <= entry_diff <= 5 and -5 <= exit_diff <= 5:
                possible_doubles.append({
                    'Nº de tarjeta': comercio_row['Nº de tarjeta'],
                    'Transacción_Gopass': gopass_row['Transacción'],
                    'Comercio_entrada': comercio_entry,
                    'Comercio_salida': comercio_exit,
                    'Gopass_entrada': gopass_entry,
                    'Gopass_salida': gopass_exit,
                    'Diferencia_entrada_min': entry_diff,
                    'Diferencia_salida_min': exit_diff,
                    'llave_validacion_comercio': comercio_row['llave_validacion'],
                    'llave_validacion_gopass': gopass_row['llave_validacion']
                })
        
        progress_bar.progress((i + 1) / total_comercio)
    
    possible_doubles_df = pd.DataFrame(possible_doubles)
    st.write(f"Posibles dobles cobros encontrados: {len(possible_doubles_df)}")
    
    return possible_doubles_df

def find_confirmed_double_billing(possible_doubles_df, comercio_df_original, gopass_df):
    """
    Encuentra dobles cobros confirmados usando matrículas
    """
    st.write("### ✅ Confirmando Dobles Cobros...")
    
    confirmed_doubles = []
    
    for _, possible_double in possible_doubles_df.iterrows():
        card_number = possible_double['Nº de tarjeta']
        
        # Buscar registros del comercio con este número de tarjeta
        card_records = comercio_df_original[comercio_df_original['Nº de tarjeta'] == card_number]
        
        # Encontrar matrícula válida
        valid_plate = None
        for _, record in card_records.iterrows():
            plate = record['Matrícula']
            if is_valid_license_plate(plate):
                valid_plate = str(plate).strip().upper()
                break
        
        if valid_plate:
            # Crear llave de confirmación del comercio
            comercio_confirmation_key = f"{possible_double['llave_validacion_comercio']}|{valid_plate}"
            
            # Buscar el registro correspondiente en Gopass
            gopass_transaction = possible_double['Transacción_Gopass']
            gopass_record = gopass_df[gopass_df['Transacción'] == gopass_transaction]
            
            if not gopass_record.empty:
                gopass_plate = str(gopass_record['Placa Vehiculo'].iloc[0]).strip().upper()
                gopass_confirmation_key = f"{possible_double['llave_validacion_gopass']}|{gopass_plate}"
                
                # Verificar si las llaves de confirmación coinciden
                if comercio_confirmation_key == gopass_confirmation_key:
                    confirmed_doubles.append({
                        'Nº de tarjeta': card_number,
                        'Transacción_Gopass': gopass_transaction,
                        'Matrícula_Comercio': valid_plate,
                        'Placa_Gopass': gopass_plate,
                        'Comercio_entrada': possible_double['Comercio_entrada'],
                        'Comercio_salida': possible_double['Comercio_salida'],
                        'Gopass_entrada': possible_double['Gopass_entrada'],
                        'Gopass_salida': possible_double['Gopass_salida'],
                        'llave_confirmacion_comercio': comercio_confirmation_key,
                        'llave_confirmacion_gopass': gopass_confirmation_key
                    })
    
    confirmed_doubles_df = pd.DataFrame(confirmed_doubles)
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
                comercio_df = pd.read_csv(comercio_file)
                st.info("Archivo CSV cargado y convertido internamente.")
            else:
                comercio_df = pd.read_excel(comercio_file)
        
        # Leer base de Gopass
        with st.spinner("Cargando base de Gopass..."):
            gopass_df = pd.read_excel(gopass_file)
        
        st.success("✅ Ambos archivos cargados correctamente!")
        
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
            comercio_filtered, comercio_keys = process_comercio_base(comercio_df)
            
            # Procesar base de Gopass
            gopass_processed = process_gopass_base(gopass_df)
            
            # Buscar posibles dobles cobros
            possible_doubles = find_possible_double_billing(comercio_keys, gopass_processed)
            
            if len(possible_doubles) > 0:
                # Mostrar posibles dobles cobros
                st.subheader("⚠️ Posibles Dobles Cobros")
                st.dataframe(possible_doubles, use_container_width=True)
                
                # Buscar dobles cobros confirmados
                confirmed_doubles = find_confirmed_double_billing(
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
