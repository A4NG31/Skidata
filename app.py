import streamlit as st
import pandas as pd
import numpy as np
import io
import re
from datetime import datetime, timedelta

# -------------------------
# CONFIG STREAMLIT
# -------------------------
st.set_page_config(
    page_title="Detector de Dobles Cobros",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------
# UTIL: detectar nombres de columnas (robusto)
# -------------------------
def find_col(df, candidates):
    cols = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        lc = cand.lower().strip()
        if lc in cols:
            return cols[lc]
    # buscar por inclusión
    for cand in candidates:
        for c in df.columns:
            if cand.lower().strip() in c.lower():
                return c
    return None

# -------------------------
# UTIL: parse fechas con 'a. m.' / 'p. m.' y variantes
# -------------------------
def parse_spanish_datetime(s):
    if pd.isna(s):
        return None
    if isinstance(s, datetime):
        return s
    s = str(s).replace("\u202f", " ").replace("\xa0", " ").strip()  # quitar NBSP
    s = re.sub(r"\s+", " ", s)
    # normalizar AM/PM en español a AM/PM en inglés
    s = s.replace("a. m.", "AM").replace("a.m.", "AM").replace("a m", "AM")
    s = s.replace("p. m.", "PM").replace("p.m.", "PM").replace("p m", "PM")
    # intentar distintos formatos
    patterns = [
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %I:%M:%S%p",
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M"
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    # último recurso: pandas
    try:
        return pd.to_datetime(s, dayfirst=True, errors="coerce")
    except Exception:
        return None

# -------------------------
# CARGA Y PROCESAMIENTO COMERCIO
# -------------------------
def load_and_process_comercio(uploaded_file):
    # leer csv o excel
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file, dtype=str)
            # convertir a excel en memoria (requisito pedido): lo guardamos como bytes para descarga si se quiere
            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine="openpyxl") as w:
                df.to_excel(w, index=False, sheet_name="base_comercio")
            excel_buf.seek(0)
        else:
            df = pd.read_excel(uploaded_file, dtype=str)
            excel_buf = None
    except Exception as e:
        st.error(f"Error leyendo Base del Comercio: {e}")
        return pd.DataFrame(), None

    # normalizar columnas
    df.columns = [c.strip() for c in df.columns]
    # lower for identification
    cols_lower = [c.lower() for c in df.columns]

    # localizar columnas requeridas (variantes)
    col_nro = find_col(df, ["Nº de tarjeta", "nº de tarjeta", "nro de tarjeta", "numero de tarjeta", "n° de tarjeta", "nro_tarjeta"])
    col_tarjeta = find_col(df, ["Tarjeta", "tarjeta"])
    col_fecha = find_col(df, ["Fecha/Hora", "Fecha", "fecha/hora", "fecha hora", "fecha/hora"])
    col_mov = find_col(df, ["Movimiento", "movimiento"])
    col_matricula = find_col(df, ["Matrícula", "Matricula", "matrícula", "matricula", "placa"])

    if not col_nro or not col_tarjeta or not col_fecha or not col_mov:
        st.error("La Base del Comercio no contiene alguna(s) columna(s) requerida(s): Nº de tarjeta, Tarjeta, Fecha/Hora, Movimiento.")
        return pd.DataFrame(), excel_buf

    # quitar filas totalmente vacías
    df = df.dropna(how="all").copy()

    # normalizar tarjeta filtro
    df[col_tarjeta] = df[col_tarjeta].astype(str).str.strip()

    # filtrar solo los registros con tarjeta == "TiqueteVehiculo" o "Una salida 01"
    mask_tarjeta = df[col_tarjeta].str.lower().isin(["tiquetevehiculo".lower(), "una salida 01".lower(), "una salida 01".lower()])
    df = df[mask_tarjeta].copy()

    # parse fecha/hora
    df["_parsed_fecha"] = df[col_fecha].apply(parse_spanish_datetime)
    # drop rows without parsed date
    df = df[~df["_parsed_fecha"].isna()].copy()

    # normalizar movimiento
    df[col_mov] = df[col_mov].astype(str).str.strip()

    # identificador unico
    df[col_nro] = df[col_nro].astype(str).str.strip()

    return df, excel_buf

# -------------------------
# CARGA Y PROCESAMIENTO GOPASS
# -------------------------
def load_and_process_gopass(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file, dtype=str)
    except Exception as e:
        st.error(f"Error leyendo Base de Gopass: {e}")
        return pd.DataFrame()

    df.columns = [c.strip() for c in df.columns]
    col_trans = find_col(df, ["Transacción", "Transaccion", "transacción", "transaccion", "id"])
    col_fecha_ent = find_col(df, ["Fecha de entrada", "Fecha entrada", "fecha entrada", "fecha_de_entrada"])
    col_fecha_sal = find_col(df, ["Fecha de salida", "Fecha salida", "fecha salida", "fecha_de_salida"])
    col_placa = find_col(df, ["Placa Vehiculo", "Placa", "placa", "placa vehiculo", "placa_vehiculo"])

    if not col_trans or not col_fecha_ent or not col_fecha_sal:
        st.error("La Base de Gopass no contiene alguna(s) columna(s) requerida(s): Transacción, Fecha de entrada, Fecha de salida.")
        return pd.DataFrame()

    df = df.dropna(how="all").copy()

    # parse fechas (convertir y truncar minuto/segundo a 0 según requisito)
    df["_parsed_fecha_ent_original"] = df[col_fecha_ent].apply(parse_spanish_datetime)
    df["_parsed_fecha_sal_original"] = df[col_fecha_sal].apply(parse_spanish_datetime)

    # según requisito: tomar solo año, mes, día, hora (no minuto ni segundo)
    def truncate_to_hour(dt):
        if pd.isna(dt) or dt is None:
            return None
        return dt.replace(minute=0, second=0, microsecond=0)

    df["_parsed_fecha_ent"] = df["_parsed_fecha_ent_original"].apply(truncate_to_hour)
    df["_parsed_fecha_sal"] = df["_parsed_fecha_sal_original"].apply(truncate_to_hour)

    df[col_trans] = df[col_trans].astype(str).str.strip()
    if col_placa:
        df[col_placa] = df[col_placa].astype(str).str.strip()
    else:
        df["__placa_missing__"] = ""

    return df

# -------------------------
# CONSTRUCCIÓN LLAVES (Comercio)
# -------------------------
def build_llaves_comercio(df_com):
    # columnas detectadas
    col_nro = find_col(df_com, ["Nº de tarjeta", "nro de tarjeta", "numero de tarjeta", "n° de tarjeta"])
    col_mov = find_col(df_com, ["Movimiento", "movimiento"])
    col_fecha = find_col(df_com, ["Fecha/Hora", "Fecha", "fecha/hora", "fecha hora"])
    col_matricula = find_col(df_com, ["Matrícula", "Matricula", "matricula", "placa"])

    rows = []
    # agrupar por Nº de tarjeta
    for id_val, g in df_com.groupby(col_nro):
        # buscar fila de Entrada y Salida
        # movimientos pueden tener variaciones de caps
        entrada = g[g[col_mov].str.lower().str.contains("entrada", na=False)]
        salida = g[g[col_mov].str.lower().str.contains("salida", na=False)]
        # preferir primer registro si hay multiples
        if entrada.empty or salida.empty:
            continue
        dt_entrada = entrada["_parsed_fecha"].iloc[0]
        dt_salida = salida["_parsed_fecha"].iloc[0]
        # crear llave validacion (usamos full datetime ISO para precisión)
        llave_validacion = f"{dt_entrada.isoformat()}|{dt_salida.isoformat()}"
        # guardar matrícula candidata (buscar entre todos registros de este id)
        matriculas = g[col_matricula].dropna().astype(str).str.strip().unique() if col_matricula else []
        rows.append({
            "nro_tarjeta": id_val,
            "fecha_entrada": dt_entrada,
            "fecha_salida": dt_salida,
            "llave_validacion": llave_validacion,
            "matriculas": list(matriculas),
            "raw_group": g
        })
    df_keys = pd.DataFrame(rows)
    return df_keys

# -------------------------
# CONSTRUCCIÓN LLAVES (Gopass)
# -------------------------
def build_llaves_gopass(df_gop):
    col_trans = find_col(df_gop, ["Transacción", "Transaccion", "transacción", "transaccion", "id"])
    col_placa = find_col(df_gop, ["Placa Vehiculo", "Placa", "placa", "placa vehiculo", "placa_vehiculo"])

    rows = []
    for id_val, g in df_gop.groupby(col_trans):
        # tomar primera fecha entrada/salida truncada a hora
        dt_ent = g["_parsed_fecha_ent"].iloc[0] if "_parsed_fecha_ent" in g.columns else None
        dt_sal = g["_parsed_fecha_sal"].iloc[0] if "_parsed_fecha_sal" in g.columns else None
        if pd.isna(dt_ent) or pd.isna(dt_sal):
            continue
        llave_validacion = f"{dt_ent.isoformat()}|{dt_sal.isoformat()}"
        placa = g[col_placa].iloc[0] if col_placa and col_placa in g.columns else ""
        rows.append({
            "transaccion": id_val,
            "fecha_entrada": dt_ent,
            "fecha_salida": dt_sal,
            "llave_validacion": llave_validacion,
            "placa": placa,
            "raw_group": g
        })
    df_keys = pd.DataFrame(rows)
    return df_keys

# -------------------------
# REGLA MATRÍCULA VÁLIDA
# -------------------------
def matricula_valida(s):
    if pd.isna(s) or not isinstance(s, str):
        return False
    s = s.strip().upper()
    return bool(re.fullmatch(r"[A-Z]{3}\d{3}", s))

# -------------------------
# BUSCAR POSIBLES DOBLES (con tolerancias)
# -------------------------
def find_posibles(df_keys_com, df_keys_gop, tol_minutes=5):
    posibles = []
    tol = timedelta(minutes=tol_minutes)
    # iterar sobre llaves comercio
    for _, row in df_keys_com.iterrows():
        e_com = row["fecha_entrada"]
        s_com = row["fecha_salida"]
        # buscar en gopass donde:
        # gop.fecha_entrada within [e_com - tol, e_com + tol]  AND
        # gop.fecha_salida within [s_com - tol, s_com + tol]
        mask = df_keys_gop.apply(
            lambda r: (abs((r["fecha_entrada"] - e_com)) <= tol) and (abs((r["fecha_salida"] - s_com)) <= tol),
            axis=1
        )
        matches = df_keys_gop[mask]
        for _, m in matches.iterrows():
            posibles.append({
                "nro_tarjeta": row["nro_tarjeta"],
                "transaccion_gopass": m["transaccion"],
                "fecha_entrada_comercio": e_com,
                "fecha_salida_comercio": s_com,
                "fecha_entrada_gopass": m["fecha_entrada"],
                "fecha_salida_gopass": m["fecha_salida"],
                "llave_validacion_comercio": row["llave_validacion"],
                "llave_validacion_gopass": m["llave_validacion"]
            })
    df_pos = pd.DataFrame(posibles)
    return df_pos

# -------------------------
# CONFIRMAR DOBLES (por matrícula/placa)
# -------------------------
def find_confirmados(df_posibles, df_keys_com, df_gop, df_comercio_raw):
    confirmados = []
    if df_posibles.empty:
        return pd.DataFrame()
    # get mapping of gopass transaccion -> placa
    col_placa = find_col(df_gop, ["Placa Vehiculo", "Placa", "placa", "placa vehiculo", "placa_vehiculo"])
    gop_map = {}
    for _, r in df_gop.iterrows():
        trans = r.get(find_col(df_gop, ["Transacción", "Transaccion", "transacción", "transaccion", "id"]))
        placa = r[col_placa] if col_placa in df_gop.columns else ""
        gop_map[trans] = placa

    for _, p in df_posibles.iterrows():
        nro = p["nro_tarjeta"]
        # obtener llaves de comercio y buscar matrícula válida entre registros originales de comercio
        # recuperar grupo original del comercio
        group = df_comercio_raw[df_comercio_raw.apply(lambda r: str(r[find_col(df_comercio_raw, ["Nº de tarjeta","nro de tarjeta","numero de tarjeta","n° de tarjeta"])]).strip() == str(nro).strip(), axis=1)]
        matricula_candidates = []
        col_matricula = find_col(df_comercio_raw, ["Matrícula", "Matricula", "matricula", "placa"])
        if col_matricula:
            for m in group[col_matricula].dropna().astype(str).str.strip().unique():
                if matricula_valida(m):
                    matricula_candidates.append(m.upper())
        if not matricula_candidates:
            # no matricula válida -> no confirmado
            continue
        # usar la primera válida
        matricula = matricula_candidates[0]
        # construir llave de confirmacion comercio (llave_validacion_comercio + matricula)
        llave_conf_com = p["llave_validacion_comercio"] + "|" + matricula
        # construir llave de confirmacion gopass (llave_validacion_gopass + placa)
        placa_gop = gop_map.get(p["transaccion_gopass"], "")
        if pd.isna(placa_gop):
            placa_gop = ""
        llave_conf_gop = p["llave_validacion_gopass"] + "|" + str(placa_gop).strip().upper()
        # comparar (exact match)
        if llave_conf_com == llave_conf_gop:
            confirmados.append({
                **p,
                "matricula_confirmada": matricula,
                "placa_gopass": placa_gop,
                "llave_confirmacion": llave_conf_com
            })
    df_conf = pd.DataFrame(confirmados)
    return df_conf

# -------------------------
# STREAMLIT UI
# -------------------------
def main():
    st.title("🔍 Detector de Dobles Cobros — Full process")
    st.markdown("Carga las dos bases (Comercio y Gopass). El sistema normaliza fechas, crea llaves y verifica posibles y confirmados.")

    c1, c2 = st.columns(2)
    with c1:
        comercio_file = st.file_uploader("Base del Comercio (xlsx o csv)", type=["xlsx", "csv"], key="comercio")
    with c2:
        gopass_file = st.file_uploader("Base de Gopass (xlsx)", type=["xlsx"], key="gopass")

    if st.button("Procesar") and comercio_file and gopass_file:
        with st.spinner("Cargando y procesando..."):
            df_com_raw, excel_buf = load_and_process_comercio(comercio_file)
            df_gop_raw = load_and_process_gopass(gopass_file)

            if df_com_raw.empty or df_gop_raw.empty:
                st.warning("Alguna base no se pudo procesar correctamente. Revisa mensajes.")
                return

            # construir llaves
            df_keys_com = build_llaves_comercio(df_com_raw)
            df_keys_gop = build_llaves_gopass(df_gop_raw)

            if df_keys_com.empty:
                st.info("No se encontraron grupos válidos (Entrada/Salida) en la Base del Comercio.")
            if df_keys_gop.empty:
                st.info("No se encontraron transacciones válidas en la Base de Gopass.")

            # buscar posibles dobles con tolerancia +-5 minutos
            df_posibles = find_posibles(df_keys_com, df_keys_gop, tol_minutes=5)
            st.success("Búsqueda de posibles dobles completada.")

            # buscar confirmados
            df_confirmados = find_confirmados(df_posibles, df_keys_com, df_gop_raw, df_com_raw)
            st.success("Validación de confirmados completada.")

        # mostrar métricas
        st.markdown("### Métricas")
        m1, m2, m3 = st.columns(3)
        m1.metric("Registros Comercio (filtrados)", len(df_com_raw))
        m2.metric("Posibles Dobles", len(df_posibles))
        m3.metric("Confirmados", len(df_confirmados))

        # mostrar tablas
        st.markdown("### Posibles Dobles")
        if not df_posibles.empty:
            st.dataframe(df_posibles.reset_index(drop=True), use_container_width=True)
            # descarga
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df_posibles.to_excel(writer, index=False, sheet_name="posibles")
            buf.seek(0)
            st.download_button("Descargar Posibles (Excel)", buf.getvalue(), file_name="posibles_dobles.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("No se encontraron posibles dobles cobros.")

        st.markdown("### Dobles Confirmados")
        if not df_confirmados.empty:
            st.dataframe(df_confirmados.reset_index(drop=True), use_container_width=True)
            buf2 = io.BytesIO()
            with pd.ExcelWriter(buf2, engine="openpyxl") as writer:
                df_confirmados.to_excel(writer, index=False, sheet_name="confirmados")
            buf2.seek(0)
            st.download_button("Descargar Confirmados (Excel)", buf2.getvalue(), file_name="confirmados_dobles.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("No se encontraron dobles cobros confirmados.")

        # si el usuario subió csv, ofrecemos excel convertido
        if excel_buf:
            st.download_button("Descargar Base Comercio convertida a Excel", excel_buf.getvalue(), file_name="base_comercio_convertida.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    elif (comercio_file or gopass_file) and not st.session_state.get("_hint_shown", False):
        st.info("Sube ambas bases y presiona 'Procesar'.")
        st.session_state["_hint_shown"] = True

if __name__ == "__main__":
    main()
