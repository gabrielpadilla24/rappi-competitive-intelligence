"""
Insights generation module.
Produces 5 actionable insights from comparative analysis data.

Each insight follows the Finding / Impact / Recommendation format.
Insights are derived dynamically from the data — they update when
underlying numbers change.

Usage:
    python -m analysis.insights
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import REPORTS_DIR


# ============================================================
# Individual insight generators
# ============================================================

def _insight_pricing(price_df: pd.DataFrame) -> dict:
    """
    Find the platform with the biggest price delta vs Rappi
    and the product where it's most visible.
    """
    if price_df.empty:
        return _empty_insight(1, "pricing")

    # Average delta across all products
    ue_avg = price_df["ue_vs_rappi_pct"].mean()
    didi_avg = price_df["didi_vs_rappi_pct"].mean()

    # Find worst-case product for the most expensive competitor
    if abs(ue_avg) >= abs(didi_avg):
        competitor = "Uber Eats"
        delta = ue_avg
        delta_col = "ue_vs_rappi_pct"
        comp_col = "ubereats_avg"
    else:
        competitor = "DiDi Food"
        delta = didi_avg
        delta_col = "didi_vs_rappi_pct"
        comp_col = "didifood_avg"

    worst_row = price_df.loc[price_df[delta_col].abs().idxmax()]
    worst_product = worst_row["product"]
    worst_delta = worst_row[delta_col]

    rappi_avg_all = price_df["rappi_avg"].mean()
    comp_avg_all = price_df[comp_col].mean()

    direction = "más caro" if delta > 0 else "más barato"
    sign = "+" if delta > 0 else ""

    return {
        "number": 1,
        "category": "pricing",
        "finding": (
            f"{competitor} cobra en promedio {sign}{delta:.1f}% que Rappi en productos de fast food "
            f"(más pronunciado en '{worst_product}': {sign}{worst_delta:.1f}%)"
        ),
        "impact": (
            f"Rappi {'tiene ventaja competitiva en precio base' if delta > 0 else 'está en desventaja de precio'} "
            f"vs {competitor}. Con fees incluidos, la diferencia real al consumidor puede ser distinta."
        ),
        "recommendation": (
            "Destacar la ventaja de precio base en la app con badges 'Mejor Precio'. "
            "Revisar política de precios en productos de combo donde el diferencial es mayor."
            if delta > 0 else
            "Revisar acuerdos de pricing con restaurantes para alinear con competidores. "
            "Considerar subsidios de precio en productos ancla como Big Mac y Whopper."
        ),
        "data_support": {
            "rappi_avg_price_mxn": round(float(rappi_avg_all), 2),
            f"{competitor.lower().replace(' ', '_')}_avg_price_mxn": round(float(comp_avg_all), 2),
            "avg_delta_pct": round(float(delta), 1),
            "worst_product": worst_product,
            "worst_delta_pct": round(float(worst_delta), 1),
        },
    }


def _insight_fees(fee_df: pd.DataFrame) -> dict:
    """
    Compare total fee burden across platforms.
    Highlight which platform is cheapest on fees and by how much.
    """
    if fee_df.empty:
        return _empty_insight(2, "fees")

    rappi_row = fee_df[fee_df["platform"] == "rappi"]
    if rappi_row.empty:
        return _empty_insight(2, "fees")

    rappi_fee = float(rappi_row["avg_total_fee"].values[0])
    rappi_pct = float(rappi_row["fee_as_pct_of_product"].values[0])

    # Compare vs cheapest competitor
    competitors = fee_df[fee_df["platform"] != "rappi"].copy()
    if competitors.empty:
        return _empty_insight(2, "fees")

    min_idx = competitors["avg_total_fee"].idxmin()
    cheapest = competitors.loc[min_idx]
    cheapest_name = str(cheapest["platform"]).replace("ubereats", "Uber Eats").replace("didifood", "DiDi Food")
    cheapest_fee = float(cheapest["avg_total_fee"])
    cheapest_pct = float(cheapest["fee_as_pct_of_product"])

    delta_abs = rappi_fee - cheapest_fee
    delta_pct = (delta_abs / cheapest_fee * 100) if cheapest_fee > 0 else 0.0
    rappi_position = "más alto" if delta_abs > 0 else "más bajo"

    return {
        "number": 2,
        "category": "fees",
        "finding": (
            f"El fee total de Rappi (${rappi_fee:.0f} = {rappi_pct:.1f}% del producto) es "
            f"{abs(delta_pct):.1f}% {rappi_position} que {cheapest_name} (${cheapest_fee:.0f} = {cheapest_pct:.1f}%)"
        ),
        "impact": (
            f"{cheapest_name} usa fees bajos como diferenciador clave. "
            "Esto puede influir en la decisión de compra cuando el precio del producto es similar."
        ),
        "recommendation": (
            "Evaluar programa de envío gratis con umbral mínimo (ej: envío $0 en pedidos >$149). "
            "Comunicar la propuesta de valor total, no solo el precio del producto."
        ),
        "data_support": {
            "rappi_avg_total_fee_mxn": round(rappi_fee, 2),
            "rappi_fee_pct_of_product": round(rappi_pct, 1),
            f"{str(cheapest['platform'])}_avg_total_fee_mxn": round(cheapest_fee, 2),
            f"{str(cheapest['platform'])}_fee_pct_of_product": round(cheapest_pct, 1),
            "delta_mxn": round(float(delta_abs), 2),
            "delta_pct": round(float(delta_pct), 1),
        },
    }


def _insight_delivery_times(time_df: pd.DataFrame) -> dict:
    """
    Find the zones where Rappi is fastest vs slowest vs competition.
    """
    if time_df.empty:
        return _empty_insight(3, "delivery_time")

    time_df = time_df.copy()

    # Overall averages
    rappi_global = time_df["rappi_avg_time"].mean()
    ue_global = time_df["ubereats_avg_time"].mean()
    didi_global = time_df["didifood_avg_time"].mean()

    # Zone where Rappi has biggest advantage (lowest time vs next fastest)
    time_df["rappi_vs_best_competitor"] = time_df.apply(
        lambda row: row["rappi_avg_time"] - min(
            v for v in [row.get("ubereats_avg_time"), row.get("didifood_avg_time")]
            if pd.notna(v)
        ) if pd.notna(row.get("rappi_avg_time")) else float("nan"),
        axis=1,
    )

    best_zone_idx = time_df["rappi_vs_best_competitor"].idxmin()
    best_zone = time_df.loc[best_zone_idx]
    worst_zone_idx = time_df["rappi_vs_best_competitor"].idxmax()
    worst_zone = time_df.loc[worst_zone_idx]

    rappi_leads = float(rappi_global) < float(ue_global) and float(rappi_global) < float(didi_global)

    return {
        "number": 3,
        "category": "delivery_time",
        "finding": (
            f"Rappi promedia {rappi_global:.0f} min de entrega vs "
            f"Uber Eats {ue_global:.0f} min y DiDi {didi_global:.0f} min. "
            f"Mayor ventaja en '{best_zone['zone_type']}' ({best_zone['rappi_vs_best_competitor']:.0f} min más rápido)."
        ),
        "impact": (
            "El tiempo de entrega es el segundo factor más importante para usuarios frecuentes. "
            f"Rappi {'lidera' if rappi_leads else 'no lidera'} en velocidad a nivel global, "
            f"con variación significativa por zona."
        ),
        "recommendation": (
            f"Destacar ventaja de velocidad en la zona '{best_zone['zone_type']}' en comunicación local. "
            f"Investigar causas del rezago en '{worst_zone['zone_type']}' "
            "(posiblemente cobertura de repartidores)."
        ),
        "data_support": {
            "rappi_global_avg_min": round(float(rappi_global), 1),
            "ubereats_global_avg_min": round(float(ue_global), 1),
            "didifood_global_avg_min": round(float(didi_global), 1),
            "best_zone_for_rappi": best_zone["zone_type"],
            "rappi_advantage_min": round(float(-best_zone["rappi_vs_best_competitor"]), 1),
            "worst_zone_for_rappi": worst_zone["zone_type"],
        },
    }


def _insight_geographic(geo_df: pd.DataFrame) -> dict:
    """
    Find the zone where Rappi is least competitive (highest rank = most expensive).
    """
    if geo_df.empty:
        return _empty_insight(4, "geographic")

    rappi_geo = geo_df[geo_df["platform"] == "rappi"].copy()
    if rappi_geo.empty:
        return _empty_insight(4, "geographic")

    # Zone where Rappi has worst rank (most expensive total price)
    worst_zone_row = rappi_geo.loc[rappi_geo["rappi_rank"].idxmax()]
    best_zone_row = rappi_geo.loc[rappi_geo["rappi_rank"].idxmin()]

    worst_zone = worst_zone_row["zone_type"]
    best_zone = best_zone_row["zone_type"]
    worst_total = float(worst_zone_row["avg_total_price"])

    # Compare Rappi vs cheapest platform in the worst zone
    zone_data = geo_df[geo_df["zone_type"] == worst_zone].copy()
    zone_data = zone_data.sort_values("avg_total_price")
    cheapest_in_worst = zone_data.iloc[0]
    cheapest_name = str(cheapest_in_worst["platform"]).replace("ubereats", "Uber Eats").replace("didifood", "DiDi Food")
    cheapest_total = float(cheapest_in_worst["avg_total_price"])

    delta_pct = (worst_total - cheapest_total) / cheapest_total * 100 if cheapest_total > 0 else 0.0

    return {
        "number": 4,
        "category": "geographic",
        "finding": (
            f"Rappi es la opción más cara en la zona '{worst_zone}' "
            f"(precio total ${worst_total:.0f}), "
            f"{delta_pct:.1f}% más que {cheapest_name} (${cheapest_total:.0f}). "
            f"Rappi tiene mejor posición en '{best_zone}'."
        ),
        "impact": (
            f"En zonas periféricas/de menor ingreso, el precio total es el factor decisivo. "
            "Perder competitividad aquí puede significar pérdida de cuota en segmentos de alto crecimiento."
        ),
        "recommendation": (
            f"Implementar fees diferenciales por zona: reducir delivery fee en '{worst_zone}' "
            "para mejorar competitividad. Evaluar partnerships locales con restaurantes en esa zona."
        ),
        "data_support": {
            "worst_zone": worst_zone,
            "rappi_avg_total_price_mxn": round(worst_total, 2),
            "cheapest_platform": str(cheapest_in_worst["platform"]),
            "cheapest_avg_total_price_mxn": round(cheapest_total, 2),
            "rappi_premium_pct": round(float(delta_pct), 1),
            "best_zone": best_zone,
        },
    }


def _insight_promotions(promo_df: pd.DataFrame) -> dict:
    """
    Compare promo aggressiveness across platforms.
    """
    if promo_df.empty:
        return _empty_insight(5, "promotions")

    most_aggressive = promo_df.loc[promo_df["promo_rate_pct"].idxmax()]
    rappi_row = promo_df[promo_df["platform"] == "rappi"]

    most_agg_name = str(most_aggressive["platform"]).replace("ubereats", "Uber Eats").replace("didifood", "DiDi Food")
    most_agg_rate = float(most_aggressive["promo_rate_pct"])

    rappi_rate = float(rappi_row["promo_rate_pct"].values[0]) if not rappi_row.empty else 0.0
    rappi_type = str(rappi_row["most_common_promo_type"].values[0]) if not rappi_row.empty else "N/A"

    delta = most_agg_rate - rappi_rate
    rappi_is_leader = most_aggressive["platform"] == "rappi"

    return {
        "number": 5,
        "category": "promotions",
        "finding": (
            f"{'Rappi lidera' if rappi_is_leader else most_agg_name + ' lidera'} en agresividad promocional "
            f"con {most_agg_rate:.0f}% de observaciones con promo activa. "
            f"Rappi registra {rappi_rate:.0f}% ({rappi_type} es el tipo más frecuente)."
        ),
        "impact": (
            "Las promociones actúan como diferenciador en la decisión de plataforma, "
            "especialmente en primera compra y reactivación de usuarios inactivos."
        ),
        "recommendation": (
            "Aumentar frecuencia de promociones de tipo 'free_delivery' en horas valle. "
            "Testear 'descuento en combo' como gancho para tickets más altos."
            if rappi_rate < most_agg_rate else
            "Mantener la presión promocional actual. Medir conversión por tipo de promo "
            "para optimizar el mix entre descuento, cashback y envío gratis."
        ),
        "data_support": {
            "rappi_promo_rate_pct": round(rappi_rate, 1),
            "most_aggressive_platform": str(most_aggressive["platform"]),
            "most_aggressive_rate_pct": round(most_agg_rate, 1),
            "rappi_most_common_promo_type": rappi_type,
            "delta_vs_most_aggressive_pct": round(float(delta), 1),
        },
    }


def _empty_insight(number: int, category: str) -> dict:
    return {
        "number": number,
        "category": category,
        "finding": "Insufficient data to generate insight.",
        "impact": "N/A",
        "recommendation": "Collect more data and re-run analysis.",
        "data_support": {},
    }


# ============================================================
# Main generate function
# ============================================================

def generate_insights(analysis_results: dict) -> list[dict]:
    """
    Generate 5 actionable insights from the comparative analysis results.

    Args:
        analysis_results: dict returned by analysis.comparative.main()

    Returns:
        List of 5 insight dicts.
    """
    insights = [
        _insight_pricing(analysis_results.get("prices", pd.DataFrame())),
        _insight_fees(analysis_results.get("fees", pd.DataFrame())),
        _insight_delivery_times(analysis_results.get("times", pd.DataFrame())),
        _insight_geographic(analysis_results.get("geographic", pd.DataFrame())),
        _insight_promotions(analysis_results.get("promotions", pd.DataFrame())),
    ]
    return insights


def save_insights(insights: list[dict], output_dir: Path = REPORTS_DIR) -> None:
    """Save insights as JSON and as human-readable TXT."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = output_dir / "top5_insights.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(insights, f, ensure_ascii=False, indent=2)

    # TXT
    txt_path = output_dir / "top5_insights.txt"
    lines = [
        "═" * 60,
        "TOP 5 COMPETITIVE INSIGHTS — Rappi vs Competencia",
        "═" * 60,
        "",
    ]
    for ins in insights:
        cat_label = ins["category"].upper().replace("_", " ")
        lines += [
            f"INSIGHT #{ins['number']} — {cat_label}",
            "─" * 40,
            f"Finding:        {ins['finding']}",
            f"Impact:         {ins['impact']}",
            f"Recommendation: {ins['recommendation']}",
        ]
        ds = ins.get("data_support", {})
        if ds:
            data_str = "  |  ".join(f"{k}={v}" for k, v in ds.items())
            lines.append(f"Data:           {data_str}")
        lines += ["", ""]

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Insights saved → {json_path}")
    print(f"Insights saved → {txt_path}")


def print_insights(insights: list[dict]) -> None:
    sep = "═" * 60
    print(f"\n{sep}")
    print("TOP 5 COMPETITIVE INSIGHTS — Rappi vs Competencia")
    print(sep)
    for ins in insights:
        cat_label = ins["category"].upper().replace("_", " ")
        print(f"\nINSIGHT #{ins['number']} — {cat_label}")
        print("─" * 40)
        print(f"Finding:        {ins['finding']}")
        print(f"Impact:         {ins['impact']}")
        print(f"Recommendation: {ins['recommendation']}")
    print(f"\n{sep}\n")


# ============================================================
# CLI
# ============================================================

def main() -> list[dict]:
    from analysis.comparative import main as run_comparative
    results = run_comparative()
    insights = generate_insights(results)
    print_insights(insights)
    save_insights(insights)
    return insights


if __name__ == "__main__":
    main()
