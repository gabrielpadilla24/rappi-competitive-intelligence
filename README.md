# 🔍 Competitive Intelligence System for Rappi

Sistema automatizado de inteligencia competitiva que recolecta, analiza y visualiza datos de plataformas de delivery en México (Rappi, Uber Eats, DiDi Food) para generar insights accionables.

## 📋 Tabla de Contenidos

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Arquitectura](#arquitectura)
- [Configuración](#configuración)
- [Uso](#uso)
- [Dashboard](#dashboard)
- [Datos Recolectados](#datos-recolectados)
- [Limitaciones](#limitaciones)
- [Consideraciones Éticas](#consideraciones-éticas)

## Overview

Este sistema resuelve la falta de visibilidad sistemática sobre cómo Rappi se compara con la competencia en variables críticas: precios, tiempos de entrega, fees y promociones.

### Plataformas cubiertas
- **Rappi** (baseline propio)
- **Uber Eats**
- **DiDi Food**

### Métricas recolectadas
- Precio de productos de referencia (Big Mac, Whopper, Combos)
- Delivery fee
- Service fee
- Tiempo estimado de entrega
- Promociones y descuentos activos
- Disponibilidad de restaurantes

### Cobertura geográfica
- 25 direcciones representativas en CDMX
- 5 niveles socioeconómicos (alto, medio-alto, medio, bajo, comercial)
- 2 ciudades secundarias (Guadalajara, Monterrey)

## Quick Start

```bash
# 1. Clonar el repositorio
git clone https://github.com/user/rappi-competitive-intelligence.git
cd rappi-competitive-intelligence

# 2. Instalar dependencias
make setup

# 3. Ejecutar scraping (demo rápido — 5 direcciones)
make scrape-quick

# 4. Generar análisis e informe
make analyze

# 5. Lanzar dashboard interactivo
make dashboard
```

## Arquitectura

```
rappi-competitive-intelligence/
├── config/
│   ├── settings.py          # Configuración global (timeouts, retries, delays)
│   ├── locations.py          # 25 direcciones con coordenadas y metadata
│   └── products.py           # Productos de referencia por categoría
├── scrapers/
│   ├── base.py               # Clase base abstracta para scrapers
│   ├── rappi_scraper.py      # Scraper de Rappi
│   ├── ubereats_scraper.py   # Scraper de Uber Eats
│   ├── didifood_scraper.py   # Scraper de DiDi Food
│   └── utils/
│       ├── anti_detection.py # Headers, stealth, rate limiting
│       ├── retry.py          # Retry con backoff exponencial
│       └── screenshot.py     # Capturas automáticas de evidencia
├── data/
│   ├── raw/                  # JSONs crudos por scrape run
│   ├── processed/            # Datos limpios y normalizados (CSV)
│   └── screenshots/          # Evidencia visual por plataforma/zona
├── analysis/
│   ├── comparative.py        # Análisis comparativo multi-plataforma
│   ├── insights.py           # Generación de Top 5 insights
│   └── visualizations.py     # Gráficos y charts
├── dashboard/
│   ├── app.py                # Dashboard Streamlit
│   └── components/           # Componentes reutilizables del dashboard
├── reports/                  # Informes generados (PDF)
├── tests/
│   ├── test_scrapers.py
│   └── test_analysis.py
├── run_scraper.py            # Entry point del scraping
├── generate_report.py        # Generador del informe ejecutivo
├── requirements.txt
├── Makefile
└── README.md
```

## Configuración

### Variables de entorno (opcional)
```bash
# .env (no requerido para ejecución básica)
GROQ_API_KEY=your_key_here      # Para insights AI-powered (opcional)
PROXY_URL=http://proxy:port     # Si usas proxies rotativos (opcional)
```

### Ajustar direcciones
Edita `config/locations.py` para agregar o modificar direcciones de scraping.

### Ajustar productos
Edita `config/products.py` para cambiar los productos de referencia.

## Uso

### Scraping completo
```bash
python run_scraper.py --locations all --platforms all
```

### Scraping selectivo
```bash
# Solo Uber Eats en zonas de alto ingreso
python run_scraper.py --platforms ubereats --zone-type high_income

# Solo Rappi en Polanco y Condesa
python run_scraper.py --platforms rappi --locations polanco,condesa

# Demo rápido (5 direcciones, todas las plataformas)
python run_scraper.py --mode quick
```

### Generar análisis
```bash
python generate_report.py
```

## Dashboard

```bash
streamlit run dashboard/app.py
```

El dashboard incluye:
- Overview ejecutivo con KPIs
- Comparativa de precios por plataforma
- Análisis de fees (delivery + service)
- Mapa de calor de competitividad por zona
- Tiempos de entrega comparados
- Feed de promociones activas
- Insights AI-powered (con Groq)

## Datos Recolectados

### Output estructurado
- `data/raw/` — JSONs individuales por observación
- `data/processed/competitive_data.csv` — Dataset consolidado
- `data/screenshots/` — Evidencia visual organizada por plataforma/zona

### Schema de datos
Ver `config/settings.py` para el schema completo de cada observación.

## Limitaciones

1. **DiDi Food**: Plataforma primarily mobile-only. Datos más limitados que Rappi/Uber Eats.
2. **Service Fee**: En algunas plataformas solo visible en el flujo de checkout.
3. **Horarios**: Los precios y disponibilidad pueden variar por hora del día.
4. **Anti-bot**: Las plataformas pueden bloquear scraping intensivo.
5. **Precios dinámicos**: Los datos representan un snapshot, no tendencias continuas.

## Consideraciones Éticas

- ✅ Se respetan los `robots.txt` de cada plataforma
- ✅ Rate limiting de 3-5 segundos entre requests
- ✅ Solo se recolectan datos públicamente visibles
- ✅ User-Agents apropiados (no impersonation maliciosa)
- ✅ No se almacenan datos personales de usuarios
- ✅ Uso exclusivo para análisis competitivo / reclutamiento
- ✅ No se sobrecargan los servidores de las plataformas

## Stack Tecnológico

| Componente | Herramienta |
|------------|-------------|
| Browser Automation | Playwright (Python) |
| Anti-detection | playwright-stealth + random delays |
| Análisis | pandas, matplotlib, seaborn |
| Dashboard | Streamlit |
| Screenshots | Playwright built-in |
| LLM Insights | Groq (Llama 3) |

---

*Desarrollado como caso técnico para el rol de AI Engineer en Rappi.*
