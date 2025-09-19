import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
import io

def main():
    st.set_page_config(
        page_title="Detector de Dobles Cobros",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🔍 Detector de Dobles Cobros")
    st.markdown("### Valida posibles dobles cobros entre Base del Comercio y Base de Gopass")
    
    # Upload sections
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 Base del Comercio")
        st.info("Formatos aceptados: Excel (.xlsx) o CSV (.csv)")
        comercio_file = st.file_uploader("Seleccionar archivo", type=['xlsx', 'csv'], key="comercio")
    
    with col2:
        st.subheader("🚗 Base de Gopass")
        st.info("Formato aceptado: Excel (.xlsx)")
        gopass_file = st.file_uploader("Seleccionar archivo", type=['xlsx'], key="gopass")
    
    if comercio_file and gopass_file:
        try:
            # Load and process files
            with st.spinner("📂 Procesando archivos..."):
                df_comercio = load_and_process_comercio(comercio_file)
                df_gopass = load_and_process_gopass(gopass_file)
            
            if df_comercio.empty or df_gopass.empty:
                st.warning("⚠️ Una o ambas bases de datos están vacías después del procesamiento")
                return
            
            # Find matches
            with st.spinner("🔍 Buscando dobles cobros..."):
                posibles_dobles = find_posibles_dobles(df_comercio, df_gopass)
                confirmados_dobles = find_confirmados_dobles(posibles_dobles, df_comercio, df_gopass)
            
            # Display results
            st.success("✅ Procesamiento completado!")
            
            # Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Registros Comercio", len(df_comercio))
            with col2:
                st.metric("Posibles Dobles", len(posibles_dobles))
            with col3:
                st.metric("Confirmados", len(confirmados_dobles))
            
            # Possible doubles section
            with st.expander("📊 Posibles Dobles Cobros", expanded=True):
                if not posibles_dobles.empty:
                    st.dataframe(posibles_dobles, use_container_width=True)
                else:
                    st.info("🎉 No se encontraron posibles dobles cobros")
            
            # Confirmed doubles section
            with st.expander("✅ Dobles Cobros Confirmados", expanded=True):
                if not confirmados_dobles.empty:
                    st.dataframe(confirmados_dobles, use_container_width=True)
                    
                    # Download button
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        confirmados_dobles.to_excel(writer, sheet_name='Dobles Confirmados', index=False)
                    
                    st.download_button(
                        label="📥 Descargar Reporte Excel",
                        data=output.getvalue(),
                        file_name="dobles_cobros_confirmados.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                else:
                    st.info("🎉 No se encontraron dobles cobros confirmados")
                
        except Exception as e:
            st.error(f"❌ Error en el procesamiento: {str(e)}")
            st.info("ℹ️ Verifica que los archivos tengan el formato correcto y las columnas esperadas")

# ... (las funciones restantes se mantienen igual que en la versión anterior)

if __name__ == "__main__":
    main()