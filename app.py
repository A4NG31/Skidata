import streamlit as st
import pandas as pd
import plotly.express as px

# -------------------
# CONFIGURACIÓN PÁGINA
# -------------------
st.set_page_config(
    page_title="GoPass - Validador de Dobles Cobros",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------
# ESTILOS CSS
# -------------------
st.markdown("""
<style>
/* Fondo general */
[data-testid="stAppViewContainer"] {
    background-color: #121212;
    color: #E0E0E0;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1b2a, #1b263b);
    color: white;
}

/* Tarjetas de métricas */
.metric-card {
    background: #1e1e1e;
    padding: 20px;
    border-radius: 15px;
    text-align: center;
    box-shadow: 0px 4px 10px rgba(0,0,0,0.6);
    border: 1px solid #0ef6cc22;
}
.metric-card h2 {
    color: #0ef6cc;
    margin: 0;
    font-size: 26px;
}
.metric-card p {
    color: #90e0ef;
    margin: 0;
    font-size: 16px;
}

/* Header principal */
.main-header {
    text-align: center;
    padding: 20px;
    margin-bottom: 20px;
}
.main-header h1 {
    color: #0ef6cc;
    font-size: 40px;
    margin-bottom: 5px;
}
.main-header h3 {
    color: #90e0ef;
    font-size: 20px;
    font-weight: normal;
}

/* Footer */
footer {
    text-align: center;
    padding: 10px;
    margin-top: 30px;
    font-size: 14px;
    color: #666;
}
</style>
""", unsafe_allow_html=True)

# -------------------
# HEADER
# -------------------
st.markdown("""
<div class="main-header">
    <h1>🚦 GoPass - Validador de Dobles Cobros</h1>
    <h3>Validación inteligente de transacciones entre bases</h3>
</div>
""", unsafe_allow_html=True)

# -------------------
# CARGA DE ARCHIVOS
# -------------------
st.sidebar.header("📂 Cargar Archivos")
file1 = st.sidebar.file_uploader("Base Comercio (Excel)", type=["xlsx"])
file2 = st.sidebar.file_uploader("Base GoPass (Excel)", type=["xlsx"])

if file1 and file2:
    try:
        base_comercio = pd.read_excel(file1)
        base_gopass = pd.read_excel(file2)

        # Normalizar nombres de columnas
        base_comercio.columns = base_comercio.columns.str.strip().str.lower()
        base_gopass.columns = base_gopass.columns.str.strip().str.lower()

        # Validación de columnas requeridas
        columnas_requeridas = {"id", "valor", "fecha"}
        if not columnas_requeridas.issubset(set(base_comercio.columns)) or not columnas_requeridas.issubset(set(base_gopass.columns)):
            st.error("❌ Las bases deben contener las columnas: id, valor, fecha")
        else:
            # -------------------
            # VALIDACIÓN DOBLES COBROS
            # -------------------
            posibles_dobles = pd.merge(
                base_comercio, base_gopass,
                on=["id", "valor", "fecha"],
                how="inner"
            )

            confirmados = posibles_dobles.copy()  # En este ejemplo, todos los encontrados se consideran confirmados

            # -------------------
            # MÉTRICAS
            # -------------------
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"""
                <div class="metric-card">
                    <h2>{len(base_comercio) + len(base_gopass):,}</h2>
                    <p>Transacciones Totales</p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div class="metric-card">
                    <h2>{len(posibles_dobles):,}</h2>
                    <p>Posibles Dobles Cobros</p>
                </div>
                """, unsafe_allow_html=True)
            with col3:
                st.markdown(f"""
                <div class="metric-card">
                    <h2>{len(confirmados):,}</h2>
                    <p>Dobles Cobros Confirmados</p>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # -------------------
            # GRAFICAS
            # -------------------
            if not confirmados.empty:
                st.subheader("📊 Análisis de Dobles Cobros Confirmados")

                # Gráfica 1: Distribución por valor
                fig1 = px.histogram(
                    confirmados,
                    x="valor",
                    nbins=20,
                    title="Distribución de valores en dobles cobros confirmados",
                    color_discrete_sequence=["#0ef6cc"]
                )
                st.plotly_chart(fig1, use_container_width=True)

                # Gráfica 2: Proporción confirmados vs no confirmados
                total = len(base_comercio) + len(base_gopass)
                fig2 = px.pie(
                    names=["Confirmados", "Otros"],
                    values=[len(confirmados), total - len(confirmados)],
                    title="Proporción de dobles cobros confirmados",
                    color_discrete_sequence=["#0ef6cc", "#90e0ef"]
                )
                st.plotly_chart(fig2, use_container_width=True)

            # -------------------
            # TABLA RESULTADOS
            # -------------------
            st.subheader("📋 Detalle de Dobles Cobros Confirmados")
            st.dataframe(confirmados)

    except Exception as e:
        st.error(f"⚠️ Error procesando archivos: {e}")

# -------------------
# FOOTER
# -------------------
st.markdown("""
<footer>
    © 2025 GoPass | Dashboard de validación de dobles cobros
</footer>
""", unsafe_allow_html=True)
