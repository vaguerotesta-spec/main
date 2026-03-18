"""
CV Adapter — Streamlit App
"""
from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
sys.path.insert(0, str(Path(__file__).parent))
import config
from pipeline import adapter, ats_validator, extractor, regenerator
st.set_page_config(page_title="CV Adapter", page_icon="📄", layout="wide")
def _init_state():
    defaults = {
        "cv_structured": None,
        "cv_position_map": None,
        "cv_raw_text": None,
        "cv_ready": False,
        "adapted_cv": None,
        "adapted_pdf_path": None,
        "ats_result": None,
        "keywords": None,
        "diff": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val
_init_state()
# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Configuración")
    api_key_input = st.text_input(
        "Anthropic API Key",
        value=config.ANTHROPIC_API_KEY,
        type="password",
        help="Tu API key de Anthropic.",
    )
    if api_key_input:
        config.ANTHROPIC_API_KEY = api_key_input
    if st.session_state.cv_ready:
        st.success("CV cargado")
        if st.button("Reemplazar CV"):
            for key in ("cv_structured", "cv_position_map", "cv_raw_text",
                        "adapted_cv", "adapted_pdf_path", "ats_result", "keywords", "diff"):
                st.session_state[key] = None
            st.session_state.cv_ready = False
            if config.ORIGINAL_CV_PATH.exists():
                config.ORIGINAL_CV_PATH.unlink()
            st.rerun()
# ── Main ──────────────────────────────────────────────────────────────────────
st.title("CV Adapter")
st.caption("Adaptá tu CV a cada búsqueda laboral, manteniendo tu diseño y siendo apto para filtros ATS.")
# PASO 1: Subir CV
if not st.session_state.cv_ready:
    st.header("Paso 1: Subí tu CV")
    st.info("Subí tu CV en PDF una sola vez. Se analizará automáticamente.")
    uploaded_file = st.file_uploader("Seleccioná tu CV (PDF)", type=["pdf"])
    if uploaded_file and st.button("Analizar CV", type="primary"):
        if not config.ANTHROPIC_API_KEY or config.ANTHROPIC_API_KEY == "your_api_key_here":
            st.error("Configurá tu Anthropic API Key en la barra lateral antes de continuar.")
            st.stop()
        with st.status("Analizando tu CV...", expanded=True) as status:
            st.write("Guardando archivo...")
            config.ORIGINAL_CV_PATH.write_bytes(uploaded_file.read())
            st.write("Extrayendo texto y estructura del PDF...")
            raw_text, position_map = extractor.extract(config.ORIGINAL_CV_PATH)
            st.session_state.cv_raw_text = raw_text
            st.session_state.cv_position_map = position_map
            st.write("Estructurando contenido con Claude...")
            try:
                cv_json = adapter.structure_cv(raw_text)
                st.session_state.cv_structured = cv_json
                st.session_state.cv_ready = True
                status.update(label="CV analizado correctamente.", state="complete")
            except Exception as e:
                status.update(label="Error al analizar el CV.", state="error")
                st.error(f"Error: {e}")
                st.stop()
        st.rerun()
    st.stop()
# PASO 2: Aviso laboral
col_left, col_right = st.columns([1, 1], gap="large")
with col_left:
    st.header("Paso 2: Búsqueda laboral")
    company = st.text_input("Empresa (opcional)", placeholder="Ej: Mercado Libre")
    role = st.text_input("Rol (opcional)", placeholder="Ej: Analista de Marketing")
    job_description = st.text_area(
        "Pegá la descripción del puesto",
        height=300,
        placeholder="Copiá y pegá el texto completo del aviso laboral aquí...",
    )
    if st.button("Adaptar CV", type="primary", disabled=not job_description.strip()):
        if not config.ANTHROPIC_API_KEY or config.ANTHROPIC_API_KEY == "your_api_key_here":
            st.error("Configurá tu Anthropic API Key en la barra lateral.")
            st.stop()
        with st.status("Adaptando tu CV...", expanded=True) as status:
            full_jd = f"Empresa: {company}\nRol: {role}\n\n{job_description}" if (company or role) else job_description
            st.write("Extrayendo keywords ATS del aviso...")
            try:
                keywords = adapter.extract_keywords(full_jd)
                st.session_state.keywords = keywords
            except Exception as e:
                st.warning(f"No se pudieron extraer keywords: {e}")
                keywords = []
                st.session_state.keywords = []
            st.write("Adaptando contenido con Claude...")
            try:
                adapted = adapter.adapt_cv(st.session_state.cv_structured, full_jd, keywords)
                st.session_state.adapted_cv = adapted
            except Exception as e:
                status.update(label="Error al adaptar el CV.", state="error")
                st.error(f"Error: {e}")
                st.stop()
            st.write("Regenerando PDF con el diseño original...")
            try:
                output_path = regenerator.regenerate(
                    original_pdf_path=config.ORIGINAL_CV_PATH,
                    original_map=st.session_state.cv_position_map,
                    adapted_cv_json=adapted,
                    original_cv_json=st.session_state.cv_structured,
                )
                st.session_state.adapted_pdf_path = output_path
            except Exception as e:
                status.update(label="Error al regenerar el PDF.", state="error")
                st.error(f"Error: {e}")
                st.stop()
            st.write("Validando compatibilidad ATS...")
            try:
                ats = ats_validator.validate(output_path, keywords)
                st.session_state.ats_result = ats
            except Exception as e:
                st.warning(f"No se pudo validar ATS: {e}")
                st.session_state.ats_result = None
            st.session_state.diff = ats_validator.diff_cv_texts(
                st.session_state.cv_structured, adapted
            )
            status.update(label="CV adaptado con éxito.", state="complete")
        st.rerun()
# PASO 3: Resultados
with col_right:
    if st.session_state.adapted_pdf_path:
        st.header("Resultado")
        pdf_bytes = Path(st.session_state.adapted_pdf_path).read_bytes()
        st.download_button(
            label="Descargar CV adaptado (PDF)",
            data=pdf_bytes,
            file_name="cv_adaptado.pdf",
            mime="application/pdf",
            type="primary",
        )
        ats = st.session_state.ats_result
        if ats:
            st.subheader("Score ATS")
            score_color = "green" if ats.score >= 70 else "orange" if ats.score >= 50 else "red"
            st.markdown(f"<h2 style='color:{score_color}'>{ats.score}/100</h2>", unsafe_allow_html=True)
            if ats.keywords_found:
                st.success(f"Keywords presentes ({len(ats.keywords_found)}): {', '.join(ats.keywords_found)}")
            if ats.keywords_missing:
                st.warning(f"Keywords faltantes ({len(ats.keywords_missing)}): {', '.join(ats.keywords_missing)}")
            for w in ats.warnings:
                st.error(w)
        st.subheader("Preview del CV adaptado")
        try:
            st.image(extractor.pdf_page_to_image_bytes(st.session_state.adapted_pdf_path), use_column_width=True)
        except Exception:
            st.info("Preview no disponible.")
    else:
        st.header("Vista previa de tu CV")
        try:
            st.image(extractor.pdf_page_to_image_bytes(config.ORIGINAL_CV_PATH), use_column_width=True)
        except Exception:
            st.info("Preview no disponible.")
# DIFF
if st.session_state.diff:
    st.divider()
    st.header(f"Cambios realizados ({len(st.session_state.diff)})")
    st.caption("Revisá cada cambio antes de enviar tu CV.")
    for change in st.session_state.diff:
        with st.expander(change["section"]):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Original**")
                st.markdown(
                    f"<div style='background:#fff3f3;padding:10px;border-radius:5px;border-left:3px solid #ff4444'>{change['original']}</div>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown("**Adaptado**")
                st.markdown(
                    f"<div style='background:#f3fff3;padding:10px;border-radius:5px;border-left:3px solid #44bb44'>{change['adapted']}</div>",
                    unsafe_allow_html=True,
                )
elif st.session_state.adapted_cv:
    st.divider()
    st.success("No se realizaron cambios en el contenido (ya estaba bien alineado con el puesto).")
if st.session_state.keywords:
    with st.expander("Keywords ATS detectados en el aviso"):
        st.write(", ".join(st.session_state.keywords))
