"""
Streamlit dashboard for Competitive Intelligence System.

Pages:
1. Executive Overview — KPIs, scorecard, last scrape timestamp
2. Price Comparison — Filters by platform/product/zone, bar charts
3. Fee Analysis — Delivery + service fee breakdown
4. Delivery Times — Distribution and heatmap by zone
5. Promotions — Active promotions feed by competitor
6. Geographic Map — CDMX map with competitiveness overlay
7. AI Insights — LLM-generated executive summary (Groq)

TODO: Implement in Phase 6
"""

import streamlit as st


def main():
    st.set_page_config(
        page_title="Rappi Competitive Intelligence",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("🔍 Competitive Intelligence Dashboard")
    st.markdown("### Sistema de Inteligencia Competitiva — Rappi vs Competencia")

    st.info("⚠️ Dashboard en construcción. Ejecuta `make scrape` primero para generar datos.")

    # Sidebar
    with st.sidebar:
        st.header("Filtros")
        st.selectbox("Plataforma", ["Todas", "Rappi", "Uber Eats", "DiDi Food"])
        st.selectbox("Zona", ["Todas", "Alto Ingreso", "Medio-Alto", "Medio", "Bajo", "Comercial"])
        st.selectbox("Restaurante", ["Todos", "McDonald's", "Burger King"])

    # Placeholder tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview", "💰 Precios", "🚚 Delivery", "🎯 Promociones", "🤖 AI Insights"
    ])

    with tab1:
        st.header("Executive Overview")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Direcciones Scrapeadas", "0")
        col2.metric("Plataformas", "0")
        col3.metric("Productos Comparados", "0")
        col4.metric("Último Scrape", "—")

    with tab2:
        st.header("Comparativa de Precios")
        st.markdown("_Gráficos de comparación de precios por plataforma y producto._")

    with tab3:
        st.header("Análisis de Delivery")
        st.markdown("_Fees, tiempos de entrega, y cobertura por zona._")

    with tab4:
        st.header("Promociones Activas")
        st.markdown("_Feed de promociones por competidor._")

    with tab5:
        st.header("AI-Powered Insights")
        st.markdown("_Resumen ejecutivo generado por IA._")


if __name__ == "__main__":
    main()
