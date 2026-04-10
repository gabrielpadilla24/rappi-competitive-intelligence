"""
AI-powered executive summary generator using Groq.

If GROQ_API_KEY is set in the environment, generates a markdown summary
by sending the top-5 insights + key metrics to the LLM.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import GROQ_API_KEY


def generate_ai_summary(insights: list[dict], metrics: dict) -> str:
    """
    Generate a concise executive summary using Groq.

    Args:
        insights: list of insight dicts (from top5_insights.json)
        metrics: dict of key KPIs (platform averages, deltas, etc.)

    Returns:
        Markdown-formatted executive summary string.
    """
    if not GROQ_API_KEY:
        return "_Configura `GROQ_API_KEY` en `.env` para habilitar resúmenes AI._"

    try:
        from groq import Groq
    except ImportError:
        return "_`groq` package no instalado. Ejecuta `pip install groq`._"

    client = Groq(api_key=GROQ_API_KEY)

    # Build a compact context string
    insight_lines = []
    for ins in insights:
        insight_lines.append(
            f"- [{ins['category'].upper()}] {ins['finding']} "
            f"→ {ins['recommendation']}"
        )

    metric_lines = [f"- {k}: {v}" for k, v in metrics.items()]

    prompt = (
        "Eres un analista de estrategia de negocio. "
        "Basado en los siguientes datos de inteligencia competitiva de plataformas de delivery en México, "
        "genera un resumen ejecutivo en español de máximo 300 palabras en formato markdown. "
        "El resumen debe incluir: situación actual de Rappi vs competencia, "
        "principales amenazas y oportunidades, y 3 recomendaciones prioritarias.\n\n"
        "**KEY METRICS:**\n"
        + "\n".join(metric_lines)
        + "\n\n**TOP INSIGHTS:**\n"
        + "\n".join(insight_lines)
    )

    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=600,
    )

    return response.choices[0].message.content
