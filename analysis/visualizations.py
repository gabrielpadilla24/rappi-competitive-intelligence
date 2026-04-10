"""
Visualization module.
Generates 8 presentation-quality charts for the competitive intelligence report.

Outputs are saved as PNG to reports/charts/.

Usage:
    python -m analysis.visualizations
"""

import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — safe for all environments
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns

warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import REPORTS_DIR, PLATFORM_COLORS, PLATFORM_LABELS

# ============================================================
# Style constants
# ============================================================

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "figure.figsize": (12, 6),
    "figure.dpi": 150,
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 12,
    "legend.fontsize": 10,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
})

COLORS = PLATFORM_COLORS
LABELS = PLATFORM_LABELS
PLATFORM_ORDER = ["rappi", "ubereats", "didifood"]

ZONE_ORDER = [
    "high_income",
    "medium_high_income",
    "medium_income",
    "low_income",
    "commercial",
]
ZONE_LABELS = {
    "high_income": "Alto Ingreso",
    "medium_high_income": "Medio-Alto",
    "medium_income": "Medio",
    "low_income": "Bajo Ingreso",
    "commercial": "Comercial",
}

# Short product names for axis labels
PRODUCT_SHORT = {
    "Big Mac": "Big Mac",
    "Combo Big Mac Mediano": "Combo Big Mac",
    "McNuggets 10 piezas": "McNuggets 10",
    "Whopper": "Whopper",
    "Combo Whopper Mediano": "Combo Whopper",
}


def _save(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  Saved → {path.name}")


def _platform_handles() -> list:
    return [
        mpatches.Patch(color=COLORS[p], label=LABELS[p])
        for p in PLATFORM_ORDER
    ]


# ============================================================
# Chart 1: Grouped bar — Price per product per platform
# ============================================================

def plot_price_comparison(df: pd.DataFrame, charts_dir: Path) -> None:
    rows = df[df["product_price_mxn"].notna() & (df["product_name"] != "")]
    pivot = (
        rows.groupby(["product_name", "platform"])["product_price_mxn"]
        .mean()
        .unstack("platform")
        .reindex(columns=PLATFORM_ORDER)
    )

    products = [PRODUCT_SHORT.get(p, p) for p in pivot.index]
    x = np.arange(len(products))
    width = 0.25

    fig, ax = plt.subplots(figsize=(13, 6))
    for i, platform in enumerate(PLATFORM_ORDER):
        values = pivot.get(platform, pd.Series(dtype=float))
        bars = ax.bar(
            x + i * width,
            values.reindex(pivot.index).fillna(0),
            width,
            label=LABELS[platform],
            color=COLORS[platform],
            alpha=0.88,
        )
        for bar, val in zip(bars, values.reindex(pivot.index)):
            if pd.notna(val) and val > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 1.5,
                    f"${val:.0f}",
                    ha="center", va="bottom", fontsize=8, color="#333333",
                )

    ax.set_xticks(x + width)
    ax.set_xticklabels(products, rotation=15, ha="right")
    ax.set_ylabel("Precio Promedio (MXN)")
    ax.set_title("Comparación de Precios por Plataforma")
    ax.legend(handles=_platform_handles(), loc="upper left")
    ax.set_ylim(0, pivot.max().max() * 1.20)
    fig.tight_layout()
    _save(fig, charts_dir / "01_price_comparison.png")


# ============================================================
# Chart 2: Stacked bar — Total cost breakdown (Combo Big Mac)
# ============================================================

def plot_total_cost_breakdown(df: pd.DataFrame, charts_dir: Path) -> None:
    product_name = "Combo Big Mac Mediano"
    rows = df[
        (df["product_name"] == product_name)
        & df["product_price_mxn"].notna()
        & df["delivery_fee_mxn"].notna()
    ]

    if rows.empty:
        # Fallback to any available product
        rows = df[df["product_price_mxn"].notna() & df["delivery_fee_mxn"].notna()]
        product_name = rows["product_name"].mode()[0] if not rows.empty else "Producto"

    agg = (
        rows.groupby("platform")
        .agg(
            product=("product_price_mxn", "mean"),
            delivery=("delivery_fee_mxn", "mean"),
            service=("service_fee_mxn", "mean"),
        )
        .reindex(PLATFORM_ORDER)
        .fillna(0)
    )

    fig, ax = plt.subplots(figsize=(9, 6))
    x = np.arange(len(PLATFORM_ORDER))
    plat_labels = [LABELS[p] for p in PLATFORM_ORDER]

    component_colors = ["#4C72B0", "#DD8452", "#55A868"]
    component_labels = ["Precio Producto", "Tarifa de Envío", "Tarifa de Servicio"]

    bottoms = np.zeros(len(PLATFORM_ORDER))
    for col, color, label in zip(["product", "delivery", "service"], component_colors, component_labels):
        values = agg[col].values
        bars = ax.bar(x, values, bottom=bottoms, color=color, label=label, alpha=0.88)
        for bar, val, bot in zip(bars, values, bottoms):
            if val > 1:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bot + val / 2,
                    f"${val:.0f}",
                    ha="center", va="center", fontsize=9, color="white", fontweight="bold",
                )
        bottoms += values

    # Total annotations on top
    for i, total in enumerate(bottoms):
        ax.text(i, total + 1.5, f"${total:.0f}", ha="center", va="bottom",
                fontsize=11, fontweight="bold", color="#222222")

    ax.set_xticks(x)
    ax.set_xticklabels(plat_labels)
    ax.set_ylabel("Costo Total (MXN)")
    ax.set_title(f"Desglose del Costo Total — {PRODUCT_SHORT.get(product_name, product_name)}")
    ax.legend(loc="upper right")
    ax.set_ylim(0, bottoms.max() * 1.20)
    fig.tight_layout()
    _save(fig, charts_dir / "02_total_cost_breakdown.png")


# ============================================================
# Chart 3: Heatmap — Average total price by zone × platform
# ============================================================

def plot_geographic_heatmap(df: pd.DataFrame, charts_dir: Path) -> None:
    rows = df[df["total_price_mxn"].notna()]

    pivot = (
        rows.groupby(["zone_type", "platform"])["total_price_mxn"]
        .mean()
        .unstack("platform")
        .reindex(PLATFORM_ORDER, axis=1)
    )

    # Use zone order and short labels
    pivot = pivot.reindex([z for z in ZONE_ORDER if z in pivot.index])
    pivot.index = [ZONE_LABELS.get(z, z) for z in pivot.index]
    pivot.columns = [LABELS[p] for p in pivot.columns]

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".0f",
        cmap="RdYlGn_r",
        ax=ax,
        linewidths=0.5,
        cbar_kws={"label": "Precio Total Promedio (MXN)"},
        annot_kws={"size": 11},
    )
    ax.set_title("Precio Total Promedio por Zona y Plataforma")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=0)
    ax.tick_params(axis="y", rotation=0)
    fig.tight_layout()
    _save(fig, charts_dir / "03_geographic_heatmap.png")


# ============================================================
# Chart 4: Box / range chart — Delivery times by platform
# ============================================================

def plot_delivery_times(df: pd.DataFrame, charts_dir: Path) -> None:
    rows = df[df["delivery_time_mid"].notna()].copy()
    rows["zone_label_short"] = rows["zone_type"].map(ZONE_LABELS).fillna(rows["zone_type"])
    rows["platform_label"] = rows["platform"].map(LABELS)

    fig, ax = plt.subplots(figsize=(12, 6))

    # Grouped box plot by platform, colored by platform
    order = [LABELS[p] for p in PLATFORM_ORDER]
    bp = sns.boxplot(
        data=rows,
        x="zone_label_short",
        y="delivery_time_mid",
        hue="platform_label",
        hue_order=order,
        palette={LABELS[p]: COLORS[p] for p in PLATFORM_ORDER},
        ax=ax,
        order=[ZONE_LABELS.get(z, z) for z in ZONE_ORDER if z in rows["zone_type"].values],
        linewidth=1.2,
        fliersize=3,
    )

    ax.set_xlabel("Zona")
    ax.set_ylabel("Tiempo Estimado (min)")
    ax.set_title("Tiempos de Entrega Estimados por Plataforma")
    ax.tick_params(axis="x", rotation=15)
    ax.legend(title="Plataforma", loc="upper right")
    fig.tight_layout()
    _save(fig, charts_dir / "04_delivery_times.png")


# ============================================================
# Chart 5: Horizontal grouped bar — Fee comparison
# ============================================================

def plot_fee_comparison(df: pd.DataFrame, charts_dir: Path) -> None:
    rows = df[df["delivery_fee_mxn"].notna()]
    agg = (
        rows.groupby("platform")
        .agg(
            delivery=("delivery_fee_mxn", "mean"),
            service=("service_fee_mxn", "mean"),
        )
        .reindex(PLATFORM_ORDER)
        .fillna(0)
    )

    y = np.arange(len(PLATFORM_ORDER))
    height = 0.35
    plat_labels = [LABELS[p] for p in PLATFORM_ORDER]

    fig, ax = plt.subplots(figsize=(10, 5))

    bars_delivery = ax.barh(y + height / 2, agg["delivery"], height,
                            label="Tarifa de Envío", color="#4C72B0", alpha=0.88)
    bars_service = ax.barh(y - height / 2, agg["service"], height,
                           label="Tarifa de Servicio", color="#DD8452", alpha=0.88)

    def _annotate(bars):
        for bar in bars:
            w = bar.get_width()
            if w > 0.5:
                ax.text(w + 0.4, bar.get_y() + bar.get_height() / 2,
                        f"${w:.0f}", va="center", fontsize=9)

    _annotate(bars_delivery)
    _annotate(bars_service)

    ax.set_yticks(y)
    ax.set_yticklabels(plat_labels)
    ax.set_xlabel("Fee Promedio (MXN)")
    ax.set_title("Comparación de Fees por Plataforma")
    ax.legend(loc="lower right")
    ax.set_xlim(0, max(agg["delivery"].max(), agg["service"].max()) * 1.3)
    fig.tight_layout()
    _save(fig, charts_dir / "05_fee_comparison.png")


# ============================================================
# Chart 6: Bar — Promotion rates with % annotations
# ============================================================

def plot_promotion_rates(df: pd.DataFrame, charts_dir: Path) -> None:
    obs = df.drop_duplicates(subset=["scrape_id"])
    agg = (
        obs.groupby("platform")
        .agg(total=("scrape_id", "count"), with_promo=("promotions_count", lambda x: (x > 0).sum()))
        .reindex(PLATFORM_ORDER)
    )
    agg["rate"] = (agg["with_promo"] / agg["total"] * 100).round(1)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(
        [LABELS[p] for p in PLATFORM_ORDER],
        agg["rate"].fillna(0),
        color=[COLORS[p] for p in PLATFORM_ORDER],
        alpha=0.88,
        width=0.5,
    )
    for bar, val in zip(bars, agg["rate"].fillna(0)):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.8,
            f"{val:.0f}%",
            ha="center", va="bottom", fontsize=12, fontweight="bold",
        )

    ax.set_ylabel("% Observaciones con Promoción Activa")
    ax.set_title("Agresividad Promocional por Plataforma")
    ax.set_ylim(0, max(agg["rate"].fillna(0).max() * 1.3, 10))
    fig.tight_layout()
    _save(fig, charts_dir / "06_promotion_rates.png")


# ============================================================
# Chart 7: Radar — Multi-dimension competitive scorecard
# ============================================================

def plot_competitive_radar(df: pd.DataFrame, charts_dir: Path) -> None:
    rows = df[df["product_price_mxn"].notna() & df["delivery_fee_mxn"].notna()]

    agg = (
        rows.groupby("platform")
        .agg(
            price=("product_price_mxn", "mean"),
            delivery_fee=("delivery_fee_mxn", "mean"),
            service_fee=("service_fee_mxn", "mean"),
            time=("delivery_time_mid", "mean"),
        )
        .reindex(PLATFORM_ORDER)
    )

    obs = df.drop_duplicates(subset=["scrape_id"])
    promo_rate = (
        obs.groupby("platform")["promotions_count"]
        .apply(lambda x: (x > 0).mean() * 100)
        .reindex(PLATFORM_ORDER)
        .fillna(0)
    )
    agg["promo_rate"] = promo_rate.values

    # Normalize: for each dimension, 1 = best (cheapest/fastest/most promos)
    # For price, fee, time: lower is better → invert
    # For promos: higher is better
    dims = ["price", "delivery_fee", "service_fee", "time", "promo_rate"]
    dim_labels = ["Precio", "Tarifa Envío", "Tarifa Servicio", "Velocidad", "Promociones"]

    normalized = pd.DataFrame(index=agg.index, columns=dims, dtype=float)
    for dim in dims:
        col = agg[dim]
        col_min, col_max = col.min(), col.max()
        if col_max == col_min:
            normalized[dim] = 1.0
        elif dim == "promo_rate":
            # Higher = better
            normalized[dim] = (col - col_min) / (col_max - col_min)
        else:
            # Lower = better → invert
            normalized[dim] = 1 - (col - col_min) / (col_max - col_min)

    N = len(dims)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True})

    for platform in PLATFORM_ORDER:
        values = normalized.loc[platform].tolist()
        values += values[:1]
        ax.plot(angles, values, "o-", linewidth=2,
                color=COLORS[platform], label=LABELS[platform])
        ax.fill(angles, values, alpha=0.12, color=COLORS[platform])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dim_labels, size=11)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.5", "0.75", "1.0"], size=8, color="gray")
    ax.set_title("Scorecard Competitivo Multi-dimensión\n(1 = mejor en cada eje)",
                 size=13, fontweight="bold", pad=20)
    ax.legend(handles=_platform_handles(), loc="upper right",
              bbox_to_anchor=(1.3, 1.15))

    fig.tight_layout()
    _save(fig, charts_dir / "07_competitive_radar.png")


# ============================================================
# Chart 8: Grouped bar — Price delta vs Rappi by zone
# ============================================================

def plot_price_delta_by_zone(df: pd.DataFrame, charts_dir: Path) -> None:
    rows = df[df["product_price_mxn"].notna()]

    pivot = (
        rows.groupby(["zone_type", "platform"])["product_price_mxn"]
        .mean()
        .unstack("platform")
        .reindex(columns=PLATFORM_ORDER)
    )
    pivot = pivot.reindex([z for z in ZONE_ORDER if z in pivot.index])

    if "rappi" not in pivot.columns:
        print("  Skipping chart 08 — no Rappi data")
        return

    pivot["ue_delta"] = (pivot["ubereats"] - pivot["rappi"]) / pivot["rappi"] * 100
    pivot["didi_delta"] = (pivot["didifood"] - pivot["rappi"]) / pivot["rappi"] * 100

    zone_short = [ZONE_LABELS.get(z, z) for z in pivot.index]
    x = np.arange(len(zone_short))
    width = 0.35

    fig, ax = plt.subplots(figsize=(12, 6))

    ue_vals = pivot["ue_delta"].fillna(0).values
    didi_vals = pivot["didi_delta"].fillna(0).values

    bars_ue = ax.bar(x - width / 2, ue_vals, width,
                     color=COLORS["ubereats"], alpha=0.88, label="Uber Eats vs Rappi")
    bars_didi = ax.bar(x + width / 2, didi_vals, width,
                       color=COLORS["didifood"], alpha=0.88, label="DiDi Food vs Rappi")

    def _annotate_bar(bars, vals):
        for bar, val in zip(bars, vals):
            if abs(val) > 0.3:
                ypos = bar.get_height() + 0.3 if val >= 0 else bar.get_height() - 1.2
                ax.text(bar.get_x() + bar.get_width() / 2, ypos,
                        f"{val:+.1f}%", ha="center", va="bottom", fontsize=8)

    _annotate_bar(bars_ue, ue_vals)
    _annotate_bar(bars_didi, didi_vals)

    ax.axhline(0, color="black", linewidth=1.0, linestyle="--", alpha=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(zone_short, rotation=15, ha="right")
    ax.set_ylabel("Diferencial de Precio (%)\n(positivo = competencia más cara)")
    ax.set_title("Diferencial de Precio vs Rappi por Zona\n(+% = Rappi más barato)")
    ax.legend()
    ax.set_ylim(
        min(ue_vals.min(), didi_vals.min()) - 4,
        max(ue_vals.max(), didi_vals.max()) + 4,
    )
    fig.tight_layout()
    _save(fig, charts_dir / "08_price_delta_by_zone.png")


# ============================================================
# Main
# ============================================================

def main() -> list[Path]:
    from analysis.comparative import main as run_comparative

    results = run_comparative()
    df = results["raw"]

    charts_dir = REPORTS_DIR / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating charts → {charts_dir}/")

    plot_price_comparison(df, charts_dir)
    plot_total_cost_breakdown(df, charts_dir)
    plot_geographic_heatmap(df, charts_dir)
    plot_delivery_times(df, charts_dir)
    plot_fee_comparison(df, charts_dir)
    plot_promotion_rates(df, charts_dir)
    plot_competitive_radar(df, charts_dir)
    plot_price_delta_by_zone(df, charts_dir)

    chart_files = sorted(charts_dir.glob("*.png"))
    print(f"\n✅ {len(chart_files)} charts saved to {charts_dir}/")
    return chart_files


if __name__ == "__main__":
    main()
