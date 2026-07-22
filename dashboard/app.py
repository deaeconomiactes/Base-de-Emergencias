"""Router principal del dashboard de Emergencias Agropecuarias."""
from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="Home",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

paginas = [
    st.Page("Home.py", title="Home", icon="🌾", default=True),
    st.Page(
        "pages/1_Productores.py",
        title="Productores",
        url_path="Productores",
    ),
    st.Page(
        "pages/2_Detalle_DDJJ.py",
        title="Detalle DDJJ",
        url_path="Detalle_DDJJ",
    ),
    st.Page("pages/3_Adremas.py", title="Adremas", url_path="Adremas"),
    st.Page("pages/4_Mapa.py", title="Mapa", url_path="Mapa"),
    st.Page("pages/5_Analisis.py", title="Análisis", url_path="Analisis"),
    st.Page(
        "pages/6_Ficha_Productor.py",
        title="Ficha Productor",
        url_path="Ficha_Productor",
    ),
]

pagina_seleccionada = st.navigation(paginas)
pagina_seleccionada.run()
