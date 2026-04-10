"""
Rappi Competitive Intelligence — Streamlit Dashboard

Run from the project root:
    streamlit run dashboard/app.py
"""

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Make sure project root is on the path regardless of launch directory
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import GROQ_API_KEY

# ============================================================
# Constants
# ============================================================

PLATFORM_COLORS = {
    "rappi":    "#FF441F",
    "ubereats": "#06C167",
    "didifood": "#FF8C00",
}
PLATFORM_LABELS = {
    "rappi":    "Rappi",
    "ubereats": "Uber Eats",
    "didifood": "DiDi Food",
}
PLATFORM_ORDER = ["rappi", "ubereats", "didifood"]

ZONE_LABELS = {
    "high_income":        "Alto Ingreso",
    "medium_high_income": "Medio-Alto",
    "medium_income":      "Medio",
    "low_income":         "Bajo Ingreso",
    "commercial":         "Comercial",
}
ZONE_ORDER = ["high_income", "medium_high_income", "medium_income", "low_income", "commercial"]

CATEGORY_EMOJIS = {
    "pricing":       "💰",
    "fees":          "🏷️",
    "delivery_time": "⏱️",
    "geographic":    "🗺️",
    "promotions":    "🎯",
}

PLOTLY_TEMPLATE = "plotly_white"
PLOTLY_LAYOUT = dict(
    template=PLOTLY_TEMPLATE,
    font=dict(family="Arial", size=12),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(t=60, b=40, l=40, r=20),
)


# ============================================================
# Data loading (cached)
# ============================================================

@st.cache_data
def load_data():
    csv_path = ROOT / "data" / "processed" / "competitive_data.csv"
    if not csv_path.exists():
        st.error(
            "❌ No hay datos. Ejecuta `make sample` o "
            "`python -m scripts.generate_sample_data` primero."
        )
        st.stop()

    df = pd.read_csv(csv_path)
    numeric_cols = [
        "product_price_mxn", "delivery_fee_mxn", "service_fee_mxn",
        "estimated_time_min", "estimated_time_max", "total_price_mxn",
        "restaurant_rating",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["delivery_time_mid"] = (df["estimated_time_min"] + df["estimated_time_max"]) / 2
    df["platform_label"] = df["platform"].map(PLATFORM_LABELS)
    df["zone_label"] = df["zone_type"].map(ZONE_LABELS).fillna(df["zone_type"])

    df_valid = df[df["data_completeness"] != "failed"].copy()
    return df, df_valid


@st.cache_data
def load_insights():
    path = ROOT / "reports" / "top5_insights.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


# ============================================================
# Sidebar
# ============================================================

def render_sidebar(df_valid: pd.DataFrame):
    with st.sidebar:
        st.markdown("## 🔍 Rappi CI")
        st.markdown("**Competitive Intelligence**")
        st.divider()

        st.header("🔧 Filtros")

        selected_platforms = st.multiselect(
            "Plataformas",
            options=PLATFORM_ORDER,
            default=PLATFORM_ORDER,
            format_func=lambda x: PLATFORM_LABELS[x],
        )

        zone_options = [z for z in ZONE_ORDER if z in df_valid["zone_type"].unique()]
        selected_zones = st.multiselect(
            "Zonas",
            options=zone_options,
            default=zone_options,
            format_func=lambda x: ZONE_LABELS.get(x, x),
        )

        restaurant_options = sorted(df_valid["restaurant_name"].dropna().unique().tolist())
        selected_restaurants = st.multiselect(
            "Restaurantes",
            options=restaurant_options,
            default=restaurant_options,
        )

        st.divider()
        total_obs = len(df_valid[
            df_valid["platform"].isin(selected_platforms or PLATFORM_ORDER)
        ])
        st.caption(f"📊 {len(df_valid)} observaciones válidas")
        st.caption(f"📍 {df_valid['location_id'].nunique()} ubicaciones")
        ts = df_valid["timestamp"].max()
        st.caption(f"🕐 Último scrape: {str(ts)[:10] if pd.notna(ts) else '—'}")

    return selected_platforms, selected_zones, selected_restaurants


def apply_filters(df: pd.DataFrame, platforms, zones, restaurants) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if platforms:
        mask &= df["platform"].isin(platforms)
    if zones:
        mask &= df["zone_type"].isin(zones)
    if restaurants:
        mask &= df["restaurant_name"].isin(restaurants)
    return df[mask].copy()


# ============================================================
# Tab 1: Executive Overview
# ============================================================

def tab_overview(df_all: pd.DataFrame, df_valid: pd.DataFrame, filtered: pd.DataFrame):
    st.header("📊 Executive Overview")

    # ── KPI row ──────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📍 Ubicaciones scrapeadas", df_all["location_id"].nunique())
    c2.metric("🏪 Plataformas", df_all["platform"].nunique())
    c3.metric("🛒 Productos comparados", df_all["product_reference_id"].nunique())

    rappi_avg = filtered[filtered["platform"] == "rappi"]["product_price_mxn"].mean()
    c4.metric(
        "💵 Precio prom. Rappi",
        f"${rappi_avg:.0f}" if pd.notna(rappi_avg) else "—",
    )

    st.divider()

    col_left, col_right = st.columns([1, 1])

    # ── Scorecard table ───────────────────────────────────────
    with col_left:
        st.subheader("Scorecard Competitivo")
        rows = []
        for p in PLATFORM_ORDER:
            pf = filtered[filtered["platform"] == p]
            if pf.empty:
                continue
            rows.append({
                "Plataforma":        PLATFORM_LABELS[p],
                "Precio prom. (MXN)": round(pf["product_price_mxn"].mean(), 0) if pf["product_price_mxn"].notna().any() else None,
                "Fee total prom. (MXN)": round(
                    (pf["delivery_fee_mxn"].mean() or 0) + (pf["service_fee_mxn"].mean() or 0), 0
                ),
                "Tiempo prom. (min)": round(pf["delivery_time_mid"].mean(), 0) if pf["delivery_time_mid"].notna().any() else None,
                "Tasa promo (%)":    round(
                    (filtered[filtered["platform"] == p].drop_duplicates("scrape_id")["promotions_count"] > 0).mean() * 100, 0
                ),
            })

        if rows:
            score_df = pd.DataFrame(rows).set_index("Plataforma")
            st.dataframe(
                score_df,
                use_container_width=True,
                column_config={
                    "Precio prom. (MXN)":    st.column_config.NumberColumn(format="$%.0f"),
                    "Fee total prom. (MXN)": st.column_config.NumberColumn(format="$%.0f"),
                    "Tiempo prom. (min)":    st.column_config.NumberColumn(format="%.0f min"),
                    "Tasa promo (%)":        st.column_config.ProgressColumn(
                        format="%.0f%%", min_value=0, max_value=100
                    ),
                },
            )
        else:
            st.info("Sin datos para los filtros seleccionados.")

    # ── Radar chart ───────────────────────────────────────────
    with col_right:
        st.subheader("Scorecard Multi-dimensión")
        fig = _radar_chart(filtered)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    # ── Top 3 insights ────────────────────────────────────────
    st.divider()
    st.subheader("💡 Top 3 Insights")
    insights = load_insights()
    box_styles = [st.info, st.warning, st.success]
    for ins, box in zip(insights[:3], box_styles):
        cat_emoji = CATEGORY_EMOJIS.get(ins["category"], "📌")
        box(
            f"**{cat_emoji} {ins['category'].upper().replace('_', ' ')}** — "
            f"{ins['finding']}\n\n"
            f"**Recomendación:** {ins['recommendation']}"
        )


def _radar_chart(df: pd.DataFrame):
    rows_with_data = df[df["product_price_mxn"].notna() & df["delivery_fee_mxn"].notna()]
    if rows_with_data.empty:
        return None

    agg = (
        rows_with_data.groupby("platform")
        .agg(
            price=("product_price_mxn", "mean"),
            delivery_fee=("delivery_fee_mxn", "mean"),
            service_fee=("service_fee_mxn", "mean"),
            time=("delivery_time_mid", "mean"),
        )
        .reindex(PLATFORM_ORDER)
    )

    obs = df.drop_duplicates("scrape_id")
    promo_rate = (
        obs.groupby("platform")["promotions_count"]
        .apply(lambda x: (x > 0).mean() * 100)
        .reindex(PLATFORM_ORDER)
        .fillna(0)
    )
    agg["promo_rate"] = promo_rate.values

    dims = ["price", "delivery_fee", "service_fee", "time", "promo_rate"]
    dim_labels = ["Precio", "Tarifa Envío", "Tarifa Servicio", "Velocidad", "Promociones"]

    import numpy as np
    normalized = {}
    for dim in dims:
        col = agg[dim].fillna(agg[dim].mean())
        col_min, col_max = col.min(), col.max()
        if col_max == col_min:
            normalized[dim] = [1.0] * len(PLATFORM_ORDER)
        elif dim == "promo_rate":
            normalized[dim] = ((col - col_min) / (col_max - col_min)).tolist()
        else:
            normalized[dim] = (1 - (col - col_min) / (col_max - col_min)).tolist()

    fig = go.Figure()
    for i, platform in enumerate(PLATFORM_ORDER):
        if platform not in agg.index or agg.loc[platform].isna().all():
            continue
        values = [normalized[d][i] for d in dims] + [normalized[dims[0]][i]]
        labels = dim_labels + [dim_labels[0]]
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=labels,
            fill="toself",
            name=PLATFORM_LABELS[platform],
            line_color=PLATFORM_COLORS[platform],
            fillcolor=PLATFORM_COLORS[platform],
            opacity=0.25,
        ))

    fig.update_layout(
        **PLOTLY_LAYOUT,
        polar=dict(radialaxis=dict(visible=True, range=[0, 1], tickfont=dict(size=9))),
        title="Scorecard Multi-dimensión (1 = mejor en cada eje)",
        height=400,
    )
    return fig


# ============================================================
# Tab 2: Price Comparison
# ============================================================

def tab_prices(filtered: pd.DataFrame):
    st.header("💰 Comparativa de Precios")

    rows = filtered[filtered["product_price_mxn"].notna() & (filtered["product_name"] != "")]
    if rows.empty:
        st.warning("Sin datos de precios para los filtros seleccionados.")
        return

    # ── Grouped bar ───────────────────────────────────────────
    st.subheader("Precio Promedio por Producto y Plataforma")
    agg = (
        rows.groupby(["product_name", "platform_label"])["product_price_mxn"]
        .mean()
        .reset_index()
    )
    agg.columns = ["Producto", "Plataforma", "Precio Promedio (MXN)"]

    label_order = [PLATFORM_LABELS[p] for p in PLATFORM_ORDER if PLATFORM_LABELS[p] in agg["Plataforma"].unique()]
    color_map = {v: PLATFORM_COLORS[k] for k, v in PLATFORM_LABELS.items()}

    fig = px.bar(
        agg, x="Producto", y="Precio Promedio (MXN)", color="Plataforma",
        barmode="group",
        color_discrete_map=color_map,
        category_orders={"Plataforma": label_order},
        text="Precio Promedio (MXN)",
        labels={"Precio Promedio (MXN)": "Precio (MXN)"},
    )
    fig.update_traces(texttemplate="$%{text:.0f}", textposition="outside")
    fig.update_layout(**PLOTLY_LAYOUT, title="Comparación de Precios por Producto")
    st.plotly_chart(fig, use_container_width=True)

    # ── Pivot table with deltas ───────────────────────────────
    st.subheader("Tabla Detallada con Deltas vs Rappi")
    pivot = (
        rows.groupby(["product_name", "platform"])["product_price_mxn"]
        .mean()
        .unstack("platform")
        .reindex(columns=PLATFORM_ORDER)
        .round(2)
    )
    pivot.index.name = "Producto"
    pivot.columns = [PLATFORM_LABELS[p] for p in PLATFORM_ORDER if p in pivot.columns]

    if "Rappi" in pivot.columns:
        if "Uber Eats" in pivot.columns:
            pivot["Δ UE vs Rappi"] = ((pivot["Uber Eats"] - pivot["Rappi"]) / pivot["Rappi"] * 100).round(1)
        if "DiDi Food" in pivot.columns:
            pivot["Δ DiDi vs Rappi"] = ((pivot["DiDi Food"] - pivot["Rappi"]) / pivot["Rappi"] * 100).round(1)

    col_cfg = {
        c: st.column_config.NumberColumn(format="$%.2f")
        for c in ["Rappi", "Uber Eats", "DiDi Food"]
        if c in pivot.columns
    }
    for delta_col in ["Δ UE vs Rappi", "Δ DiDi vs Rappi"]:
        if delta_col in pivot.columns:
            col_cfg[delta_col] = st.column_config.NumberColumn(format="%.1f%%")

    st.dataframe(pivot.reset_index(), use_container_width=True, column_config=col_cfg)

    # ── Per-product geographic breakdown ─────────────────────
    st.subheader("Variación Geográfica por Producto")
    product_options = sorted(rows["product_name"].dropna().unique().tolist())
    selected_product = st.selectbox("Selecciona un producto:", product_options)

    prod_rows = rows[rows["product_name"] == selected_product]
    if not prod_rows.empty:
        geo_agg = (
            prod_rows.groupby(["zone_label", "platform_label"])["product_price_mxn"]
            .mean()
            .reset_index()
        )
        geo_agg.columns = ["Zona", "Plataforma", "Precio (MXN)"]
        fig2 = px.bar(
            geo_agg, x="Zona", y="Precio (MXN)", color="Plataforma",
            barmode="group",
            color_discrete_map=color_map,
            category_orders={
                "Plataforma": label_order,
                "Zona": [ZONE_LABELS.get(z, z) for z in ZONE_ORDER],
            },
            title=f"Precio de '{selected_product}' por Zona y Plataforma",
        )
        fig2.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig2, use_container_width=True)


# ============================================================
# Tab 3: Delivery & Fees
# ============================================================

def tab_delivery(filtered: pd.DataFrame):
    st.header("🚚 Delivery & Fees")

    rows_fee = filtered[filtered["delivery_fee_mxn"].notna()]
    if rows_fee.empty:
        st.warning("Sin datos de fees para los filtros seleccionados.")
        return

    # ── Stacked total cost breakdown ──────────────────────────
    st.subheader("Desglose del Costo Total por Plataforma")

    product_options_fee = [p for p in ["Combo Big Mac Mediano", "Combo Whopper Mediano"]
                           if p in filtered["product_name"].unique()]
    if not product_options_fee:
        product_options_fee = filtered["product_name"].dropna().unique().tolist()

    ref_product = st.selectbox(
        "Producto de referencia:",
        product_options_fee,
        key="fee_product_select",
    )

    cost_rows = rows_fee[rows_fee["product_name"] == ref_product] if ref_product else rows_fee

    cost_agg = (
        cost_rows.groupby("platform")
        .agg(
            Producto=("product_price_mxn", "mean"),
            Envío=("delivery_fee_mxn", "mean"),
            Servicio=("service_fee_mxn", "mean"),
        )
        .reindex(PLATFORM_ORDER)
        .fillna(0)
        .reset_index()
    )
    cost_agg["platform_label"] = cost_agg["platform"].map(PLATFORM_LABELS)

    fig_stack = go.Figure()
    component_colors = {"Producto": "#4C72B0", "Envío": "#DD8452", "Servicio": "#55A868"}
    for comp, color in component_colors.items():
        fig_stack.add_trace(go.Bar(
            name=comp,
            x=cost_agg["platform_label"],
            y=cost_agg[comp],
            marker_color=color,
            text=cost_agg[comp].round(0),
            texttemplate="$%{text:.0f}",
            textposition="inside",
        ))

    fig_stack.update_layout(
        **PLOTLY_LAYOUT,
        barmode="stack",
        title=f"Costo Total Desglosado — {ref_product}",
        yaxis_title="Costo (MXN)",
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    # ── Horizontal fee comparison ─────────────────────────────
    st.subheader("Comparación de Fees por Plataforma")
    c1, c2 = st.columns(2)

    fee_agg = (
        rows_fee.groupby("platform")
        .agg(Envío=("delivery_fee_mxn", "mean"), Servicio=("service_fee_mxn", "mean"))
        .reindex(PLATFORM_ORDER)
        .fillna(0)
        .reset_index()
    )
    fee_agg["platform_label"] = fee_agg["platform"].map(PLATFORM_LABELS)

    fig_fee = go.Figure()
    for comp, color in [("Envío", "#4C72B0"), ("Servicio", "#DD8452")]:
        fig_fee.add_trace(go.Bar(
            name=comp,
            y=fee_agg["platform_label"],
            x=fee_agg[comp],
            orientation="h",
            marker_color=color,
            text=fee_agg[comp].round(1),
            texttemplate="$%{text:.0f}",
            textposition="outside",
        ))
    fig_fee.update_layout(
        **PLOTLY_LAYOUT,
        barmode="group",
        title="Fees por Plataforma",
        xaxis_title="Fee Promedio (MXN)",
    )
    with c1:
        st.plotly_chart(fig_fee, use_container_width=True)

    # Fee as % of product
    fee_agg["fee_pct"] = (
        (fee_agg["Envío"] + fee_agg["Servicio"])
        / rows_fee.groupby("platform")["product_price_mxn"].mean().reindex(PLATFORM_ORDER).values
        * 100
    ).round(1)

    fig_pct = px.bar(
        fee_agg, x="platform_label", y="fee_pct",
        color="platform_label",
        color_discrete_map={PLATFORM_LABELS[p]: PLATFORM_COLORS[p] for p in PLATFORM_ORDER},
        text="fee_pct",
        labels={"platform_label": "Plataforma", "fee_pct": "% del Precio"},
    )
    fig_pct.update_traces(texttemplate="%{text:.1f}%", textposition="outside", showlegend=False)
    fig_pct.update_layout(**PLOTLY_LAYOUT, title="Fees como % del Precio del Producto")
    with c2:
        st.plotly_chart(fig_pct, use_container_width=True)

    # ── Delivery time box plot ────────────────────────────────
    st.subheader("Tiempos de Entrega por Plataforma")
    time_rows = filtered[filtered["delivery_time_mid"].notna()]
    if not time_rows.empty:
        fig_time = px.box(
            time_rows,
            x="platform_label",
            y="delivery_time_mid",
            color="platform_label",
            color_discrete_map={PLATFORM_LABELS[p]: PLATFORM_COLORS[p] for p in PLATFORM_ORDER},
            category_orders={"platform_label": [PLATFORM_LABELS[p] for p in PLATFORM_ORDER]},
            labels={"platform_label": "Plataforma", "delivery_time_mid": "Tiempo Estimado (min)"},
            points="all",
        )
        fig_time.update_traces(showlegend=False)
        fig_time.update_layout(**PLOTLY_LAYOUT, title="Distribución de Tiempos de Entrega")
        st.plotly_chart(fig_time, use_container_width=True)


# ============================================================
# Tab 4: Geographic Analysis
# ============================================================

def tab_geographic(filtered: pd.DataFrame):
    st.header("🗺️ Análisis Geográfico")

    # ── Heatmap ───────────────────────────────────────────────
    st.subheader("Heatmap: Precio Total Promedio por Zona y Plataforma")
    hm_rows = filtered[filtered["total_price_mxn"].notna()]
    if not hm_rows.empty:
        pivot_hm = (
            hm_rows.groupby(["zone_type", "platform"])["total_price_mxn"]
            .mean()
            .unstack("platform")
            .reindex([z for z in ZONE_ORDER if z in hm_rows["zone_type"].unique()])
            .reindex(columns=PLATFORM_ORDER)
            .round(1)
        )
        pivot_hm.index = [ZONE_LABELS.get(z, z) for z in pivot_hm.index]
        pivot_hm.columns = [PLATFORM_LABELS.get(p, p) for p in pivot_hm.columns]

        fig_hm = px.imshow(
            pivot_hm,
            text_auto=".0f",
            color_continuous_scale="RdYlGn_r",
            aspect="auto",
            labels={"color": "Precio Total Promedio (MXN)"},
        )
        fig_hm.update_layout(
            **PLOTLY_LAYOUT,
            title="Precio Total Promedio (MXN)",
            xaxis_title="",
            yaxis_title="",
        )
        st.plotly_chart(fig_hm, use_container_width=True)
    else:
        st.warning("Sin datos suficientes para el heatmap.")

    # ── Price delta by zone ───────────────────────────────────
    st.subheader("Diferencial de Precio vs Rappi por Zona")
    price_rows = filtered[filtered["product_price_mxn"].notna()]
    if not price_rows.empty:
        pivot_delta = (
            price_rows.groupby(["zone_type", "platform"])["product_price_mxn"]
            .mean()
            .unstack("platform")
            .reindex([z for z in ZONE_ORDER if z in price_rows["zone_type"].unique()])
            .reindex(columns=PLATFORM_ORDER)
        )
        pivot_delta.index = [ZONE_LABELS.get(z, z) for z in pivot_delta.index]

        if "rappi" in pivot_delta.columns:
            delta_df_rows = []
            for comp in [p for p in PLATFORM_ORDER if p != "rappi"]:
                if comp in pivot_delta.columns:
                    delta = ((pivot_delta[comp] - pivot_delta["rappi"]) / pivot_delta["rappi"] * 100).round(1)
                    for zone, val in delta.items():
                        delta_df_rows.append({
                            "Zona": zone,
                            "Competidor": PLATFORM_LABELS[comp],
                            "Delta (%)": val,
                        })
            delta_df = pd.DataFrame(delta_df_rows)
            if not delta_df.empty:
                comp_color = {PLATFORM_LABELS[p]: PLATFORM_COLORS[p]
                              for p in PLATFORM_ORDER if p != "rappi"}
                fig_delta = px.bar(
                    delta_df, x="Zona", y="Delta (%)", color="Competidor",
                    barmode="group",
                    color_discrete_map=comp_color,
                    title="Diferencial de Precio vs Rappi (+% = competencia más cara)",
                )
                fig_delta.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
                fig_delta.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig_delta, use_container_width=True)

    # ── Location detail table ─────────────────────────────────
    st.subheader("Detalle por Ubicación")
    with st.expander("Ver tabla completa", expanded=False):
        detail_cols = [
            "zone_label", "location_address", "platform_label",
            "restaurant_name", "product_name", "product_price_mxn",
            "delivery_fee_mxn", "total_price_mxn", "delivery_time_mid",
        ]
        avail_cols = [c for c in detail_cols if c in filtered.columns]
        display = filtered[avail_cols].dropna(subset=["product_price_mxn"]).copy()
        display.columns = [
            c.replace("_label", "").replace("_", " ").title()
            for c in avail_cols
        ]
        st.dataframe(display, use_container_width=True)


# ============================================================
# Tab 5: Promotions
# ============================================================

def tab_promotions(filtered: pd.DataFrame):
    st.header("🎯 Promociones")

    obs = filtered.drop_duplicates("scrape_id")

    # ── Promo rate bar ────────────────────────────────────────
    st.subheader("Agresividad Promocional por Plataforma")
    promo_rate = (
        obs.groupby("platform")
        .agg(total=("scrape_id", "count"), with_promo=("promotions_count", lambda x: (x > 0).sum()))
        .reindex(PLATFORM_ORDER)
        .reset_index()
    )
    promo_rate["rate"] = (promo_rate["with_promo"] / promo_rate["total"] * 100).round(1)
    promo_rate["platform_label"] = promo_rate["platform"].map(PLATFORM_LABELS)

    fig_rate = px.bar(
        promo_rate, x="platform_label", y="rate",
        color="platform_label",
        color_discrete_map={PLATFORM_LABELS[p]: PLATFORM_COLORS[p] for p in PLATFORM_ORDER},
        text="rate",
        labels={"platform_label": "Plataforma", "rate": "% con Promoción"},
    )
    fig_rate.update_traces(texttemplate="%{text:.0f}%", textposition="outside", showlegend=False)
    fig_rate.update_layout(**PLOTLY_LAYOUT, title="% de Observaciones con Promoción Activa",
                           yaxis_range=[0, 100])
    st.plotly_chart(fig_rate, use_container_width=True)

    # ── Promo feed ────────────────────────────────────────────
    st.subheader("Feed de Promociones Encontradas")

    promo_rows = filtered[
        filtered["promotions_description"].notna()
        & (filtered["promotions_description"].str.strip() != "")
    ].copy()

    if promo_rows.empty:
        st.info("No se encontraron promociones con los filtros actuales.")
    else:
        platform_filter = st.selectbox(
            "Filtrar por plataforma:",
            ["Todas"] + [PLATFORM_LABELS[p] for p in PLATFORM_ORDER],
            key="promo_platform_filter",
        )
        if platform_filter != "Todas":
            plat_key = {v: k for k, v in PLATFORM_LABELS.items()}[platform_filter]
            promo_rows = promo_rows[promo_rows["platform"] == plat_key]

        # Explode pipe-separated descriptions
        promo_exploded = promo_rows.copy()
        promo_exploded["promo"] = promo_exploded["promotions_description"].str.split(" | ")
        promo_exploded = promo_exploded.explode("promo")
        promo_exploded = promo_exploded[promo_exploded["promo"].str.strip() != ""]

        grouped = (
            promo_exploded
            .groupby(["platform_label", "promo"])
            .agg(count=("scrape_id", "count"), zones=("zone_label", lambda x: ", ".join(sorted(x.unique()))))
            .reset_index()
            .sort_values(["platform_label", "count"], ascending=[True, False])
        )

        for platform_lbl in grouped["platform_label"].unique():
            with st.expander(f"**{platform_lbl}**", expanded=True):
                pf_rows = grouped[grouped["platform_label"] == platform_lbl]
                for _, row in pf_rows.iterrows():
                    st.markdown(
                        f"🏷️ **{row['promo']}** &nbsp;&nbsp;"
                        f"<span style='color:gray;font-size:0.85em'>"
                        f"({row['count']} obs · {row['zones']})</span>",
                        unsafe_allow_html=True,
                    )

    # ── Promo type pie ────────────────────────────────────────
    st.subheader("Distribución de Tipos de Promoción")

    def _classify_promo(text: str) -> str:
        t = text.lower()
        if "%" in t or "off" in t or "descuento" in t:
            return "discount"
        if "gratis" in t or "envío" in t or "free" in t:
            return "free_delivery"
        if "cashback" in t:
            return "cashback"
        return "bundle"

    if not promo_rows.empty:
        all_promos = (
            promo_rows["promotions_description"]
            .str.split(" | ")
            .explode()
            .dropna()
        )
        all_promos = all_promos[all_promos.str.strip() != ""]
        type_counts = all_promos.apply(_classify_promo).value_counts().reset_index()
        type_counts.columns = ["Tipo", "Cantidad"]

        type_labels = {
            "discount": "Descuento",
            "free_delivery": "Envío Gratis",
            "cashback": "Cashback",
            "bundle": "Bundle/Combo",
        }
        type_counts["Tipo"] = type_counts["Tipo"].map(type_labels).fillna(type_counts["Tipo"])

        fig_pie = px.pie(
            type_counts, values="Cantidad", names="Tipo",
            title="Tipos de Promoción (todos los competidores)",
            hole=0.35,
        )
        fig_pie.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig_pie, use_container_width=True)


# ============================================================
# Tab 6: AI Insights
# ============================================================

def tab_ai_insights(filtered: pd.DataFrame):
    st.header("🤖 AI Insights")

    insights = load_insights()

    # ── Top 5 insight cards ───────────────────────────────────
    st.subheader("Top 5 Insights Competitivos")

    if not insights:
        st.warning("No se encontraron insights. Ejecuta `python -m analysis.insights` primero.")
    else:
        for ins in insights:
            cat_emoji = CATEGORY_EMOJIS.get(ins["category"], "📌")
            cat_label = ins["category"].upper().replace("_", " ")
            with st.expander(f"{cat_emoji} **Insight #{ins['number']} — {cat_label}**", expanded=True):
                st.markdown(f"**📋 Finding:**\n{ins['finding']}")
                st.markdown(f"**💥 Impact:**\n{ins['impact']}")
                st.markdown(f"**✅ Recommendation:**\n{ins['recommendation']}")

                ds = ins.get("data_support", {})
                if ds:
                    st.divider()
                    cols = st.columns(min(len(ds), 4))
                    for col, (key, val) in zip(cols, list(ds.items())[:4]):
                        label = key.replace("_", " ").title()
                        if isinstance(val, float):
                            display_val = f"${val:.1f}" if "price" in key or "fee" in key or "mxn" in key else f"{val:+.1f}%"
                        else:
                            display_val = str(val)
                        col.metric(label, display_val)

    # ── AI Summary via Groq ───────────────────────────────────
    st.divider()
    st.subheader("🧠 Resumen Ejecutivo AI")

    if not GROQ_API_KEY:
        st.info(
            "💡 **Configura `GROQ_API_KEY` en `.env`** para habilitar resúmenes generados por IA.\n\n"
            "```\nGROQ_API_KEY=gsk_...\n```"
        )
    else:
        # Build key metrics for the prompt
        rappi_data = filtered[filtered["platform"] == "rappi"]
        key_metrics = {
            "rappi_avg_price_mxn": round(rappi_data["product_price_mxn"].mean(), 2) if not rappi_data.empty else "N/A",
            "rappi_avg_delivery_fee_mxn": round(rappi_data["delivery_fee_mxn"].mean(), 2) if not rappi_data.empty else "N/A",
            "total_locations": filtered["location_id"].nunique(),
            "total_valid_observations": len(filtered),
        }

        if st.button("🤖 Generar Resumen Ejecutivo con AI", type="primary"):
            with st.spinner("Generando resumen con Groq LLaMA-3..."):
                from dashboard.ai_summary import generate_ai_summary
                summary = generate_ai_summary(insights, key_metrics)
                st.markdown(summary)


# ============================================================
# Main
# ============================================================

def main():
    st.set_page_config(
        page_title="Rappi Competitive Intelligence",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS
    st.markdown(
        """
        <style>
        .block-container { padding-top: 3.5rem; padding-bottom: 2rem; }
        .stMetric { background: #f8f9fa; border-radius: 8px; padding: 0.5rem 1rem; }
        /* Keep the tab bar fully visible when sticky */
        .stTabs [data-baseweb="tab-list"] {
            position: sticky;
            top: 0;
            z-index: 100;
            background-color: white;
            padding-top: 0.25rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    df_all, df_valid = load_data()

    # Sidebar filters
    sel_platforms, sel_zones, sel_restaurants = render_sidebar(df_valid)

    # Apply filters
    filtered = apply_filters(df_valid, sel_platforms, sel_zones, sel_restaurants)

    if filtered.empty:
        st.warning("⚠️ No hay datos para los filtros seleccionados. Ajusta los filtros del sidebar.")
        st.stop()

    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Executive Overview",
        "💰 Precios",
        "🚚 Delivery & Fees",
        "🗺️ Geográfico",
        "🎯 Promociones",
        "🤖 AI Insights",
    ])

    with tab1:
        tab_overview(df_all, df_valid, filtered)
    with tab2:
        tab_prices(filtered)
    with tab3:
        tab_delivery(filtered)
    with tab4:
        tab_geographic(filtered)
    with tab5:
        tab_promotions(filtered)
    with tab6:
        tab_ai_insights(filtered)


if __name__ == "__main__":
    main()
