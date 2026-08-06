"""Router principal del dashboard de Emergencias Agropecuarias."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Helpers exclusivamente visuales. Se usa una carpeta separada sin convertirla en
# paquete para no colisionar con el modulo historico dashboard/utils.py.
DISPLAY_UTILS_DIR = Path(__file__).resolve().parent / "utils"
if str(DISPLAY_UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(DISPLAY_UTILS_DIR))


st.set_page_config(
    page_title="Registro de Emergencias Agropecuarias",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

paginas = [
    st.Page("Home.py", title="🏠 Home", icon="🌾", default=True),
    st.Page("pages/4_Mapa.py", title="🗺️ Mapa", url_path="Mapa"),
    st.Page("pages/5_Analisis.py", title="📊 Análisis", url_path="Analisis"),
    st.Page(
        "pages/6_Ficha_Productor.py",
        title="👤 Ficha Productor",
        url_path="Ficha_Productor",
    ),
]

pagina_seleccionada = st.navigation(paginas)
pagina_seleccionada.run()
