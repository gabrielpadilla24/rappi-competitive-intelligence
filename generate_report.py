"""
Generate executive PDF report from analyzed competitive intelligence data.

Usage:
    python generate_report.py
    python generate_report.py --author "Gabriel Padilla"
    python generate_report.py --output reports/mi_informe.pdf
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from fpdf import FPDF

logger = logging.getLogger("report")

ROOT = Path(__file__).resolve().parent
CHARTS_DIR  = ROOT / "reports" / "charts"
INSIGHTS_PATH = ROOT / "reports" / "top5_insights.json"
CSV_PATH    = ROOT / "data" / "processed" / "competitive_data.csv"

# ── Brand palette ────────────────────────────────────────────
RAPPI_RED   = (255, 68,  31)
UE_GREEN    = (6,   193, 103)
DIDI_ORANGE = (255, 140,  0)
DARK        = (40,  40,  40)
MID_GRAY    = (100, 100, 100)
LIGHT_GRAY  = (200, 200, 200)
ACCENT_BG   = (245, 245, 245)
WHITE       = (255, 255, 255)

CATEGORY_LABELS = {
    "pricing":       "PRICING",
    "fees":          "FEES",
    "delivery_time": "DELIVERY TIME",
    "geographic":    "GEOGRAPHIC",
    "promotions":    "PROMOTIONS",
}


# ============================================================
# PDF class
# ============================================================

class CompetitiveReport(FPDF):
    """Custom FPDF subclass with header, footer, and helpers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._total_pages = 0      # filled after alias_nb_pages()

    def header(self):
        if self.page_no() <= 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 8, "Rappi Competitive Intelligence Report - Confidencial", align="R")
        self.set_draw_color(*LIGHT_GRAY)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y() + 8, 210 - self.r_margin, self.get_y() + 8)
        self.ln(10)

    def footer(self):
        if self.page_no() <= 1:
            return
        self.set_y(-14)
        self.set_draw_color(*LIGHT_GRAY)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), 210 - self.r_margin, self.get_y())
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 8, f"Página {self.page_no()}/{{nb}}", align="C")

    # ── Typography helpers ────────────────────────────────────

    def h1(self, text: str) -> None:
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(*DARK)
        self.cell(0, 12, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        # Accent underline
        self.set_draw_color(*RAPPI_RED)
        self.set_line_width(1.0)
        self.line(self.l_margin, self.get_y(), self.l_margin + 40, self.get_y())
        self.set_line_width(0.3)
        self.ln(6)

    def h2(self, text: str) -> None:
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*DARK)
        self.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def h3(self, text: str) -> None:
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 7, text.upper(), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body(self, text: str, indent: float = 0) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        self.set_x(self.l_margin + indent)
        self.multi_cell(self._width_eff - indent, 5.5, text)
        self.ln(2)

    def bullet(self, text: str, symbol: str = "-") -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        self.set_x(self.l_margin + 4)
        self.cell(6, 5.5, symbol)
        self.multi_cell(self._width_eff - 10, 5.5, text)

    def label_value(self, label: str, value: str) -> None:
        """Inline bold label + normal value on one line."""
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*DARK)
        self.cell(38, 5.5, label + ":")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*MID_GRAY)
        self.multi_cell(self._width_eff - 38, 5.5, value)

    def divider(self, y_gap_before: float = 3, y_gap_after: float = 4) -> None:
        self.ln(y_gap_before)
        self.set_draw_color(*LIGHT_GRAY)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), 210 - self.r_margin, self.get_y())
        self.ln(y_gap_after)

    # ── Chart insertion ───────────────────────────────────────

    def add_chart(self, name: str, width: float = 175, caption: str = "") -> None:
        path = CHARTS_DIR / name
        if not path.exists():
            logger.warning(f"Chart not found, skipping: {name}")
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(*MID_GRAY)
            self.cell(0, 6, f"[Gráfico no disponible: {name}]", new_x="LMARGIN", new_y="NEXT")
            self.ln(3)
            return
        x = (210 - width) / 2
        self.image(str(path), x=x, w=width)
        if caption:
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(*MID_GRAY)
            self.cell(0, 6, caption, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    # ── KPI table ─────────────────────────────────────────────

    def kpi_table(self, rows: list[tuple[str, str]]) -> None:
        """Render a 2-column (label, value) table with alternating row background."""
        col_w = (self._width_eff) / 2
        for i, (label, value) in enumerate(rows):
            if i % 2 == 0:
                self.set_fill_color(*ACCENT_BG)
            else:
                self.set_fill_color(*WHITE)
            self.set_font("Helvetica", "", 10)
            self.set_text_color(*MID_GRAY)
            self.cell(col_w, 8, f"  {label}", fill=True)
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(*DARK)
            self.cell(col_w, 8, value, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    @property
    def _width_eff(self) -> float:
        return 210 - self.l_margin - self.r_margin


# ============================================================
# Data helpers
# ============================================================

def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not CSV_PATH.exists():
        logger.error(f"CSV not found: {CSV_PATH}. Run `make sample` first.")
        sys.exit(1)
    df = pd.read_csv(CSV_PATH)
    numeric = [
        "product_price_mxn", "delivery_fee_mxn", "service_fee_mxn",
        "estimated_time_min", "estimated_time_max", "total_price_mxn",
    ]
    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["delivery_time_mid"] = (df["estimated_time_min"] + df["estimated_time_max"]) / 2
    valid = df[df["data_completeness"] != "failed"].copy()
    return df, valid


def load_insights() -> list[dict]:
    if not INSIGHTS_PATH.exists():
        logger.warning("top5_insights.json not found - insights section will be empty")
        return []
    with open(INSIGHTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _fmt(value, prefix="$", suffix="", decimals=0) -> str:
    if pd.isna(value):
        return "N/A"
    if decimals == 0:
        return f"{prefix}{value:.0f}{suffix}"
    return f"{prefix}{value:.{decimals}f}{suffix}"


# ============================================================
# Page builders
# ============================================================

def page_cover(pdf: CompetitiveReport, author: str) -> None:
    pdf.add_page()
    # Full-page background
    pdf.set_fill_color(*ACCENT_BG)
    pdf.rect(0, 0, 210, 297, "F")

    # Top accent bar
    pdf.set_fill_color(*RAPPI_RED)
    pdf.rect(0, 0, 210, 18, "F")

    # Bottom accent bar
    pdf.set_fill_color(*DARK)
    pdf.rect(0, 270, 210, 27, "F")

    # Main title
    pdf.set_y(55)
    pdf.set_font("Helvetica", "B", 36)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 14, "COMPETITIVE INTELLIGENCE", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 36)
    pdf.cell(0, 14, "REPORT", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Red divider line
    pdf.set_draw_color(*RAPPI_RED)
    pdf.set_line_width(2.0)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.set_line_width(0.3)
    pdf.ln(10)

    # Subtitle
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 8, "Rappi vs Competencia", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Mercado de Delivery - México", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)

    # Platform tags
    for label, color in [("Rappi", RAPPI_RED), ("Uber Eats", UE_GREEN), ("DiDi Food", DIDI_ORANGE)]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*WHITE)
        pdf.set_fill_color(*color)
        total_w = 35
        start_x = (210 - 3 * total_w - 2 * 4) / 2
        # We'll render all 3 inline
        break
    x_start = (210 - (35 * 3 + 4 * 2)) / 2
    for label, color in [("  Rappi  ", RAPPI_RED), ("  Uber Eats  ", UE_GREEN), ("  DiDi Food  ", DIDI_ORANGE)]:
        pdf.set_x(0)
    y_tag = pdf.get_y()
    for i, (label, color) in enumerate([("Rappi", RAPPI_RED), ("Uber Eats", UE_GREEN), ("DiDi Food", DIDI_ORANGE)]):
        tag_w = 45
        x = x_start + i * (tag_w + 6)
        pdf.set_xy(x, y_tag)
        pdf.set_fill_color(*color)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(tag_w, 10, label, align="C", fill=True)
    pdf.ln(18)

    # Date
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*MID_GRAY)
    date_str = datetime.now().strftime("%d de %B de %Y").replace(
        "January", "enero").replace("February", "febrero").replace("March", "marzo").replace(
        "April", "abril").replace("May", "mayo").replace("June", "junio").replace(
        "July", "julio").replace("August", "agosto").replace("September", "septiembre").replace(
        "October", "octubre").replace("November", "noviembre").replace("December", "diciembre")
    pdf.cell(0, 7, f"Generado el {date_str}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 7, f"Preparado por: {author}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Rol: AI Engineer", align="C", new_x="LMARGIN", new_y="NEXT")


def page_executive_summary(pdf: CompetitiveReport, df: pd.DataFrame, valid: pd.DataFrame) -> None:
    pdf.add_page()
    pdf.h1("Resumen Ejecutivo")

    n_loc    = df["location_id"].nunique()
    n_plat   = df["platform"].nunique()
    n_prod   = valid["product_reference_id"].nunique()
    n_obs    = len(df)
    rappi_v  = valid[valid["platform"] == "rappi"]
    rappi_price = rappi_v["product_price_mxn"].mean()
    rappi_fee   = (rappi_v["delivery_fee_mxn"].mean() or 0) + (rappi_v["service_fee_mxn"].mean() or 0)

    ue_price   = valid[valid["platform"] == "ubereats"]["product_price_mxn"].mean()
    didi_fee   = valid[valid["platform"] == "didifood"]["delivery_fee_mxn"].mean()
    ue_delta   = (ue_price - rappi_price) / rappi_price * 100 if rappi_price else 0
    fee_delta  = (rappi_fee - didi_fee) / didi_fee * 100 if didi_fee else 0

    summary = (
        f"Se analizaron {n_plat} plataformas de delivery (Rappi, Uber Eats y DiDi Food) en "
        f"{n_loc} ubicaciones representativas de CDMX, cubriendo 5 zonas socioeconómicas "
        f"(alto ingreso, medio-alto, medio, bajo ingreso y comercial). Se recolectaron "
        f"{n_obs} observaciones de precios, fees, tiempos de entrega y promociones para "
        f"{n_prod} productos estandarizados de McDonald's y Burger King.\n\n"
        f"Los hallazgos principales revelan que Uber Eats cobra en promedio {ue_delta:+.1f}% "
        f"respecto a Rappi en precios de producto, mientras que DiDi Food compite con fees de "
        f"entrega significativamente más bajos (${didi_fee:.0f} MXN promedio vs ${rappi_fee:.0f} MXN "
        f"de Rappi, una diferencia del {fee_delta:.0f}%). Rappi mantiene ventaja en precio base de "
        f"producto, pero enfrenta presión competitiva en la estructura de fees totales."
    )
    pdf.body(summary)
    pdf.ln(2)

    pdf.h2("Métricas Clave del Estudio")
    kpis = [
        ("Ubicaciones scrapeadas",  str(n_loc)),
        ("Plataformas analizadas",  str(n_plat)),
        ("Productos de referencia", str(n_prod)),
        ("Observaciones totales",   str(n_obs)),
        ("Precio prom. Rappi",      _fmt(rappi_price)),
        ("Fee total prom. Rappi",   _fmt(rappi_fee)),
        ("Fee total prom. DiDi",    _fmt(didi_fee)),
        ("Delta precio UE vs Rappi", f"{ue_delta:+.1f}%"),
    ]
    pdf.kpi_table(kpis)


def page_methodology(pdf: CompetitiveReport, valid: pd.DataFrame) -> None:
    pdf.add_page()
    pdf.h1("Metodología")

    pdf.h2("1. Scope")
    pdf.body(
        "El análisis cubre tres plataformas de delivery en México: Rappi (baseline), "
        "Uber Eats y DiDi Food. Las observaciones se realizaron en Ciudad de México, "
        "con dos restaurantes de referencia - McDonald's y Burger King - "
        "seleccionados por su presencia uniforme en todas las plataformas y zonas."
    )

    pdf.h2("2. Ubicaciones Seleccionadas")
    zones_info = [
        ("Alto Ingreso (5)",       "Polanco, Santa Fe, Condesa, Roma Norte, Lomas"),
        ("Medio-Alto (5)",         "Del Valle, Mixcoac, Florida, Country Club"),
        ("Medio (5)",              "Narvarte, Agrícola Oriental, Letrán Valle"),
        ("Bajo Ingreso (5)",       "Iztapalapa, Tláhuac, GAM, Ecatepec, Satélite"),
        ("Comercial / Centro (3)", "Reforma, Centro Histórico, Chapultepec"),
    ]
    for zone, detail in zones_info:
        pdf.bullet(f"{zone}: {detail}")
    pdf.ln(2)

    pdf.h2("3. Productos de Referencia")
    products = [
        "Big Mac (McDonald's)",
        "Combo Big Mac Mediano (McDonald's)",
        "McNuggets 10 piezas (McDonald's)",
        "Whopper (Burger King)",
        "Combo Whopper Mediano (Burger King)",
    ]
    for p in products:
        pdf.bullet(p)
    pdf.ln(2)

    pdf.h2("4. Stack Técnico")
    pdf.body(
        "El sistema de scraping fue desarrollado en Python utilizando Playwright para "
        "automatización de navegadores con técnicas de anti-detección (rotación de "
        "User-Agent, delays aleatorios, emulación humana). Los datos se procesan con "
        "pandas y se almacenan en formato JSON normalizado. El análisis y visualizaciones "
        "se generan con matplotlib/seaborn, y el dashboard interactivo con Streamlit + Plotly."
    )

    pdf.h2("5. Limitaciones")
    limitations = [
        "DiDi Food: plataforma primarily mobile-only; datos web limitados (~30% failed).",
        "Snapshot temporal: los datos representan un momento puntual, no tendencias.",
        "Service fee: en algunas plataformas solo es visible durante el checkout.",
        "Cobertura geográfica: enfoque en CDMX; pendiente validación en GDL y MTY.",
        "Precios dinámicos: pueden variar por hora, demanda y ubicación exacta.",
    ]
    for lim in limitations:
        pdf.bullet(lim, symbol="(!)")
    pdf.ln(2)


def page_price_analysis(pdf: CompetitiveReport, valid: pd.DataFrame) -> None:
    pdf.add_page()
    pdf.h1("Análisis Comparativo de Precios")

    rappi_avg  = valid[valid["platform"] == "rappi"]["product_price_mxn"].mean()
    ue_avg     = valid[valid["platform"] == "ubereats"]["product_price_mxn"].mean()
    didi_avg   = valid[valid["platform"] == "didifood"]["product_price_mxn"].mean()
    ue_delta   = (ue_avg - rappi_avg) / rappi_avg * 100 if rappi_avg else 0
    didi_delta = (didi_avg - rappi_avg) / rappi_avg * 100 if rappi_avg else 0

    pdf.h2("Precios por Producto y Plataforma")
    pdf.add_chart("01_price_comparison.png", width=175,
                  caption="Fig. 1 - Precio promedio por producto (MXN)")
    pdf.body(
        f"Uber Eats cobra en promedio {ue_delta:+.1f}% más que Rappi en todos los productos "
        f"analizados. DiDi Food se ubica {didi_delta:+.1f}% respecto a Rappi. "
        f"La mayor brecha se observa en productos de combo, donde los precios de Uber Eats "
        f"superan consistentemente a Rappi. Rappi mantiene ventaja de precio base en la "
        f"mayoría de los SKUs evaluados."
    )

    pdf.h2("Desglose del Costo Total")
    pdf.add_chart("02_total_cost_breakdown.png", width=140,
                  caption="Fig. 2 - Costo total desglosado: producto + envío + servicio (MXN)")

    rappi_fee = (valid[valid["platform"]=="rappi"]["delivery_fee_mxn"].mean() or 0) + \
                (valid[valid["platform"]=="rappi"]["service_fee_mxn"].mean() or 0)
    didi_fee  = valid[valid["platform"]=="didifood"]["delivery_fee_mxn"].mean() or 0
    fee_gap   = rappi_fee - didi_fee

    pdf.body(
        f"Al incluir fees de envío y servicio, el panorama cambia: DiDi Food presenta el "
        f"costo total más bajo gracias a sus fees reducidos (${didi_fee:.0f} MXN promedio vs "
        f"${rappi_fee:.0f} MXN de Rappi, diferencia de ${fee_gap:.0f} MXN). "
        f"Esta es la principal palanca de diferenciación de DiDi Food frente a Rappi."
    )


def page_geo_times(pdf: CompetitiveReport, valid: pd.DataFrame) -> None:
    pdf.add_page()
    pdf.h1("Análisis Geográfico y Tiempos de Entrega")

    pdf.h2("Variabilidad Geográfica de Precios")
    pdf.add_chart("03_geographic_heatmap.png", width=160,
                  caption="Fig. 3 - Precio total promedio por zona y plataforma (MXN)")

    # Find most/least competitive zone for Rappi from data
    geo = (
        valid.groupby(["zone_type", "platform"])["total_price_mxn"]
        .mean()
        .unstack("platform")
    )
    if "rappi" in geo.columns:
        worst_zone = geo["rappi"].idxmax() if not geo["rappi"].isna().all() else "N/A"
        best_zone  = geo["rappi"].idxmin() if not geo["rappi"].isna().all() else "N/A"
        zone_map = {
            "high_income": "alto ingreso", "medium_high_income": "medio-alto",
            "medium_income": "medio", "low_income": "bajo ingreso", "commercial": "comercial",
        }
        worst_lbl = zone_map.get(worst_zone, worst_zone)
        best_lbl  = zone_map.get(best_zone, best_zone)
    else:
        worst_lbl = best_lbl = "N/A"

    pdf.body(
        f"El heatmap revela heterogeneidad significativa en competitividad según zona. "
        f"Rappi presenta el costo total más alto en la zona de {worst_lbl}, donde la "
        f"competencia (especialmente DiDi Food) ofrece mejores precios combinados. "
        f"La zona {best_lbl} es donde Rappi es más competitivo en precio total."
    )

    pdf.h2("Tiempos de Entrega por Plataforma")
    pdf.add_chart("04_delivery_times.png", width=175,
                  caption="Fig. 4 - Distribución de tiempos de entrega por plataforma (min)")

    rappi_t = valid[valid["platform"]=="rappi"]["delivery_time_mid"].mean()
    ue_t    = valid[valid["platform"]=="ubereats"]["delivery_time_mid"].mean()
    didi_t  = valid[valid["platform"]=="didifood"]["delivery_time_mid"].mean()

    fastest = min(
        [(t, n) for t, n in [(rappi_t, "Rappi"), (ue_t, "Uber Eats"), (didi_t, "DiDi Food")]
         if pd.notna(t)],
        key=lambda x: x[0],
    )
    pdf.body(
        f"En tiempos de entrega, {fastest[1]} lidera con {fastest[0]:.0f} min promedio. "
        f"Rappi registra {rappi_t:.0f} min promedio, Uber Eats {ue_t:.0f} min. "
        f"La variabilidad es mayor en zonas periféricas (bajo ingreso), donde todos los "
        f"operadores presentan tiempos más altos por menor densidad de repartidores."
    )


def page_fees_promos(pdf: CompetitiveReport, valid: pd.DataFrame) -> None:
    pdf.add_page()
    pdf.h1("Estructura de Fees y Promociones")

    pdf.h2("Comparación de Fees por Plataforma")
    pdf.add_chart("05_fee_comparison.png", width=155,
                  caption="Fig. 5 - Tarifa de envío y servicio por plataforma (MXN)")

    rappi_del = valid[valid["platform"]=="rappi"]["delivery_fee_mxn"].mean()
    rappi_svc = valid[valid["platform"]=="rappi"]["service_fee_mxn"].mean()
    didi_del  = valid[valid["platform"]=="didifood"]["delivery_fee_mxn"].mean()
    ue_del    = valid[valid["platform"]=="ubereats"]["delivery_fee_mxn"].mean()

    pdf.body(
        f"DiDi Food tiene la estructura de fees más baja del mercado: tarifa de envío de "
        f"${didi_del:.0f} MXN promedio vs ${rappi_del:.0f} MXN de Rappi y "
        f"${ue_del:.0f} MXN de Uber Eats. Rappi adicionalmente cobra una tarifa de servicio "
        f"de ${rappi_svc:.0f} MXN promedio. Esta diferencia de fees es el principal driver "
        f"de ventaja de costo total de DiDi frente a los demás operadores."
    )

    pdf.h2("Agresividad Promocional")
    pdf.add_chart("06_promotion_rates.png", width=140,
                  caption="Fig. 6 - % de observaciones con promoción activa por plataforma")

    obs = valid.drop_duplicates("scrape_id")
    promo_rates = {
        p: round((obs[obs["platform"]==p]["promotions_count"] > 0).mean() * 100, 0)
        for p in ["rappi", "ubereats", "didifood"]
    }
    top_plat = max(promo_rates, key=promo_rates.get)
    top_label = {"rappi": "Rappi", "ubereats": "Uber Eats", "didifood": "DiDi Food"}[top_plat]

    pdf.body(
        f"{top_label} lidera en agresividad promocional con {promo_rates[top_plat]:.0f}% "
        f"de observaciones con al menos una promoción activa "
        f"(Rappi: {promo_rates['rappi']:.0f}%, Uber Eats: {promo_rates['ubereats']:.0f}%, "
        f"DiDi Food: {promo_rates['didifood']:.0f}%). "
        f"Las promociones se concentran en descuentos directos y envío gratis, "
        f"siendo el principal mecanismo de adquisición y retención de usuarios."
    )


def page_insights(pdf: CompetitiveReport, insights: list[dict]) -> None:
    pdf.add_page()
    pdf.h1("Top 5 Insights Accionables")

    if not insights:
        pdf.body("No se encontraron insights. Ejecuta `python -m analysis.insights` primero.")
        return

    cat_labels = {
        "pricing":       "PRICING",
        "fees":          "FEES",
        "delivery_time": "DELIVERY TIME",
        "geographic":    "GEOGRAPHIC",
        "promotions":    "PROMOTIONS",
    }

    for ins in insights:
        # Check if we need a new page (need ~55mm for a full insight block)
        if pdf.get_y() > 220:
            pdf.add_page()

        cat = cat_labels.get(ins.get("category", ""), ins.get("category", "").upper())

        # Insight header bar
        pdf.set_fill_color(*ACCENT_BG)
        pdf.set_draw_color(*RAPPI_RED)
        pdf.set_line_width(0.5)
        bar_y = pdf.get_y()
        pdf.rect(pdf.l_margin, bar_y, pdf._width_eff, 9, "FD")
        pdf.set_xy(pdf.l_margin + 3, bar_y + 1.5)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*RAPPI_RED)
        pdf.cell(20, 6, f"#{ins.get('number', '?')}")
        pdf.set_text_color(*DARK)
        pdf.cell(0, 6, f"- {cat}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_line_width(0.3)
        pdf.ln(3)

        pdf.label_value("Finding",   ins.get("finding", ""))
        pdf.label_value("Impacto",   ins.get("impact", ""))
        pdf.label_value("Rec.",      ins.get("recommendation", ""))
        pdf.divider(y_gap_before=2, y_gap_after=5)


def page_scorecard(pdf: CompetitiveReport, valid: pd.DataFrame) -> None:
    pdf.add_page()
    pdf.h1("Scorecard Competitivo Multi-dimensión")

    pdf.add_chart("07_competitive_radar.png", width=140,
                  caption="Fig. 7 - Radar normalizado (1 = mejor en cada eje)")

    pdf.h2("Resumen por Dimensión")

    # Build summary table
    rows_data = []
    for p in ["rappi", "ubereats", "didifood"]:
        pf = valid[valid["platform"] == p]
        label = {"rappi": "Rappi", "ubereats": "Uber Eats", "didifood": "DiDi Food"}[p]
        price = _fmt(pf["product_price_mxn"].mean())
        fee   = _fmt((pf["delivery_fee_mxn"].mean() or 0) + (pf["service_fee_mxn"].mean() or 0))
        time_ = f"{pf['delivery_time_mid'].mean():.0f} min" if pf["delivery_time_mid"].notna().any() else "N/A"
        obs_p = valid.drop_duplicates("scrape_id")
        promo = f"{(obs_p[obs_p['platform']==p]['promotions_count']>0).mean()*100:.0f}%"
        rows_data.append((label, price, fee, time_, promo))

    # Header row
    col_w = pdf._width_eff / 5
    headers = ["Plataforma", "Precio prom.", "Fee total", "Tiempo prom.", "Tasa promo"]
    pdf.set_fill_color(40, 40, 40)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 9)
    for h in headers:
        pdf.cell(col_w, 8, h, align="C", fill=True, border=0)
    pdf.ln()

    # Data rows
    for i, (plat, price, fee, time_, promo) in enumerate(rows_data):
        pdf.set_fill_color(*(ACCENT_BG if i % 2 == 0 else WHITE))
        pdf.set_text_color(*DARK)
        pdf.set_font("Helvetica", "B" if plat == "Rappi" else "", 9)
        pdf.cell(col_w, 7, plat, align="C", fill=True)
        pdf.set_font("Helvetica", "", 9)
        for val in [price, fee, time_, promo]:
            pdf.cell(col_w, 7, val, align="C", fill=True)
        pdf.ln()

    pdf.ln(6)
    pdf.body(
        "Rappi posee ventaja en precio base de producto pero enfrenta presión de DiDi Food "
        "en fees totales y de Uber Eats en penetración. La ventaja más sostenible de Rappi "
        "radica en su ecosistema (RappiPay, RappiPrime) y mayor densidad de restaurantes, "
        "factores no capturados en este análisis de precio-fee."
    )


def page_next_steps(pdf: CompetitiveReport) -> None:
    pdf.add_page()
    pdf.h1("Limitaciones y Próximos Pasos")

    pdf.h2("Limitaciones del Análisis")
    limitations = [
        ("DiDi Food web",      "Plataforma primarily mobile-only; ~30% de observaciones fallidas. Requiere acceso a API o scraping de app móvil."),
        ("Snapshot temporal",  "Los datos representan un momento puntual. No permiten análisis de tendencias o estacionalidad."),
        ("Service fee",        "En algunas plataformas el service fee solo es visible durante el checkout. Puede estar subrepresentado."),
        ("Cobertura",          "El análisis se concentra en CDMX. La dinámica competitiva puede diferir en GDL, MTY y ciudades secundarias."),
        ("Precios dinámicos",  "Los precios de delivery varían por hora (surge), demanda y ubicación exacta. Este análisis captura una muestra."),
    ]
    for label, text in limitations:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK)
        pdf.set_x(pdf.l_margin + 4)
        pdf.cell(6, 5.5, "(!)")
        pdf.cell(32, 5.5, label + ":")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*MID_GRAY)
        pdf.multi_cell(0, 5.5, text)
    pdf.ln(4)

    pdf.h2("Próximos Pasos Recomendados")
    next_steps = [
        "Automatizar el scraping con GitHub Actions (cron diario) para capturar tendencias temporales y detectar cambios de precio en tiempo real.",
        "Expandir la cobertura a Guadalajara, Monterrey y Puebla para validar si las dinámicas de CDMX son representativas del mercado nacional.",
        "Agregar verticales de retail (OXXO, 7-Eleven, supermercados) para comparar Rappi Market vs competidores de conveniencia.",
        "Integrar con datos internos de Rappi (pedidos, GMV, retención) para correlacionar precio/fee con market share real.",
        "Implementar alertas automáticas via Slack/email cuando un competidor modifica sus fees o lanza una nueva promoción.",
    ]
    for i, step in enumerate(next_steps, 1):
        if pdf.get_y() > 260:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*RAPPI_RED)
        pdf.set_x(pdf.l_margin + 2)
        pdf.cell(8, 5.5, f"{i}.")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*DARK)
        pdf.multi_cell(0, 5.5, step)
        pdf.ln(1)

    # Closing statement
    pdf.ln(6)
    pdf.divider()
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 6,
             "Este informe fue generado automáticamente por el sistema Rappi Competitive Intelligence.",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6,
             "Para preguntas o acceso a datos crudos, contactar al equipo de AI Engineering.",
             align="C", new_x="LMARGIN", new_y="NEXT")


# ============================================================
# Main report generator
# ============================================================

def generate_report(
    author: str = "AI Engineer",
    output_path: str = "reports/competitive_report.pdf",
) -> Path:
    """Generate the full PDF report and return the output path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Loading data...")
    df, valid = load_data()
    insights  = load_insights()

    logger.info("Building PDF...")
    pdf = CompetitiveReport(orientation="P", unit="mm", format="A4")
    pdf.set_margins(left=18, top=18, right=18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.alias_nb_pages()

    page_cover(pdf, author)
    page_executive_summary(pdf, df, valid)
    page_methodology(pdf, valid)
    page_price_analysis(pdf, valid)
    page_geo_times(pdf, valid)
    page_fees_promos(pdf, valid)
    page_insights(pdf, insights)
    page_scorecard(pdf, valid)
    page_next_steps(pdf)

    pdf.output(str(output_path))
    logger.info(f"Report saved -> {output_path}  ({output_path.stat().st_size // 1024} KB)")
    print(f"\n[OK] PDF generado: {output_path}  ({output_path.stat().st_size // 1024} KB)")
    return output_path


# ============================================================
# CLI
# ============================================================

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Generate executive PDF report for Rappi Competitive Intelligence"
    )
    parser.add_argument(
        "--author",
        default="AI Engineer",
        help="Author name shown on the cover page (default: 'AI Engineer')",
    )
    parser.add_argument(
        "--output",
        default="reports/competitive_report.pdf",
        help="Output file path (default: reports/competitive_report.pdf)",
    )
    args = parser.parse_args()
    generate_report(author=args.author, output_path=args.output)


if __name__ == "__main__":
    main()
