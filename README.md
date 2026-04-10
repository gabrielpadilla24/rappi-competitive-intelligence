# Competitive Intelligence System for Rappi

Sistema automatizado de inteligencia competitiva que recolecta, analiza y visualiza datos de plataformas de delivery en México.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Tests](https://img.shields.io/badge/Tests-85%20passing-green)
![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red)

## Tabla de Contenidos
- [Quick Start](#quick-start)
- [Que hace este sistema](#que-hace-este-sistema)
- [Arquitectura](#arquitectura)
- [Como ejecutar](#como-ejecutar)
- [Dashboard](#dashboard)
- [Informe PDF](#informe-pdf)
- [Stack Tecnologico](#stack-tecnologico)
- [Limitaciones Conocidas](#limitaciones-conocidas)
- [Consideraciones Eticas](#consideraciones-eticas)
- [Tests](#tests)

## Quick Start

```bash
# 1. Clonar e instalar
git clone https://github.com/user/rappi-competitive-intelligence.git
cd rappi-competitive-intelligence
make setup

# 2. Generar datos de ejemplo (no requiere browser)
make sample

# 3. Ejecutar analisis completo
python -m analysis.comparative
python -m analysis.insights
python -m analysis.visualizations

# 4. Generar informe PDF
python generate_report.py --author "Tu Nombre"

# 5. Lanzar dashboard interactivo
make dashboard
```

> **Nota**: El repo ya incluye datos de ejemplo, graficos, insights y el PDF generados.
> Puedes abrir `reports/competitive_report.pdf` y ejecutar `make dashboard` directamente.

## Que hace este sistema

### Plataformas analizadas
| Plataforma | Metodo | Estado |
|------------|--------|--------|
| Rappi | Playwright + network interception | Implementado |
| Uber Eats | Playwright + DOM parsing | Implementado |
| DiDi Food | Playwright mobile emulation | Limitado (mobile-only) |

### Metricas recolectadas
- Precio de productos de referencia (Big Mac, Whopper, Combos, McNuggets)
- Delivery fee y Service fee
- Tiempo estimado de entrega (min-max)
- Promociones y descuentos activos
- Disponibilidad de restaurantes
- Rating y numero de reviews

### Cobertura geografica
- 25 direcciones en CDMX (5 zonas socioeconomicas)
- 2 ciudades secundarias (Guadalajara, Monterrey)

### Outputs del sistema
1. **Datos crudos** - JSONs individuales por observacion (`data/raw/`)
2. **CSV consolidado** - Dataset limpio para analisis (`data/processed/competitive_data.csv`)
3. **8 graficos** de calidad presentacion (`reports/charts/`)
4. **Top 5 Insights** accionables con Finding/Impact/Recommendation (`reports/top5_insights.json`)
5. **Dashboard interactivo** Streamlit con 6 tabs y filtros (`dashboard/app.py`)
6. **Informe ejecutivo PDF** de 13+ paginas (`reports/competitive_report.pdf`)

## Arquitectura

```
rappi-competitive-intelligence/
├── config/                    # Configuracion (locations, products, settings)
├── scrapers/                  # Scrapers por plataforma (Rappi, UberEats, DiDi)
│   └── utils/                 # Anti-detection, retry, screenshots, parsers
├── scripts/                   # Generador de datos sinteticos + consolidador
├── analysis/                  # Analisis comparativo, insights, visualizaciones
├── dashboard/                 # Dashboard Streamlit + AI summary
├── data/
│   ├── raw/                   # JSONs individuales por scrape
│   ├── processed/             # CSV consolidado
│   └── screenshots/           # Evidencia visual
├── reports/
│   ├── charts/                # 8 graficos PNG
│   ├── competitive_report.pdf # Informe ejecutivo
│   └── top5_insights.json     # Insights accionables
├── tests/                     # 85 tests (pytest)
├── run_scraper.py             # Entry point del scraping
├── generate_report.py         # Generador de PDF
├── Makefile                   # Todos los comandos
└── requirements.txt
```

## Como ejecutar

### Opcion A: Con datos de ejemplo (sin browser)
```bash
make sample              # Genera datos sinteticos realistas
make consolidate         # Consolida a CSV
python -m analysis.comparative
python -m analysis.insights
python -m analysis.visualizations
python generate_report.py --author "Tu Nombre"
make dashboard           # Lanza Streamlit en localhost:8501
```

### Opcion B: Scraping real (requiere Playwright + internet)
```bash
make setup                              # Instala deps + Playwright
python run_scraper.py --mode quick      # 6 ubicaciones, 3 plataformas
python run_scraper.py --mode full       # 23 ubicaciones
python run_scraper.py --mode all        # 25 ubicaciones (+ ciudades sec.)
```

### Opciones del scraper
```bash
# Filtrar por plataforma
python run_scraper.py --platforms rappi,ubereats

# Filtrar por zona
python run_scraper.py --zone-type high_income

# Ubicaciones especificas
python run_scraper.py --locations polanco,condesa,reforma

# Generar datos de ejemplo
python run_scraper.py --generate-sample --mode quick
```

## Dashboard

```bash
streamlit run dashboard/app.py
```

6 tabs interactivos:
1. **Executive Overview** - KPIs, scorecard, radar chart
2. **Precios** - Comparativa por producto/plataforma con drill-down
3. **Delivery & Fees** - Desglose de costos, tiempos, fees como porcentaje
4. **Geografico** - Heatmap por zona, delta de precios
5. **Promociones** - Tasa por plataforma, tipos, feed filtrable
6. **AI Insights** - Top 5 insights + resumen ejecutivo con Groq (opcional)

### Configuracion AI (opcional)
```bash
# Agrega en .env para habilitar resumenes AI:
GROQ_API_KEY=your_key_here
```

## Informe PDF

```bash
python generate_report.py --author "Gabriel Padilla"
# -> reports/competitive_report.pdf
```

El informe incluye: portada, resumen ejecutivo, metodologia, analisis de precios/fees/tiempos, analisis geografico, promociones, top 5 insights, scorecard y proximos pasos.

## Stack Tecnologico

| Componente | Herramienta |
|------------|-------------|
| Scraping | Playwright (Python) con stealth mode |
| Anti-detection | UA rotation, random delays, human simulation |
| Datos | pandas, JSON, CSV |
| Visualizacion estatica | matplotlib, seaborn |
| Visualizacion interactiva | Plotly |
| Dashboard | Streamlit |
| PDF | fpdf2 |
| LLM (opcional) | Groq (Llama 3) |
| Testing | pytest (85 tests) |

## Limitaciones Conocidas

1. **DiDi Food**: Plataforma primarily mobile-only. Datos web limitados (~30% fail rate).
2. **Service Fee**: En algunas plataformas solo visible en el flujo de checkout.
3. **Snapshot temporal**: Los datos representan un momento puntual.
4. **Precios dinamicos**: Varian por hora, demanda y ubicacion exacta.
5. **Cobertura**: Enfocado en CDMX. Pendiente validacion en otras ciudades.

## Consideraciones Eticas

Este sistema fue disenado con practicas responsables de scraping:

- Rate limiting: Delays de 3-5 segundos entre requests
- Respeto a robots.txt: Se verifican las directivas de cada plataforma
- Solo datos publicos: No se accede a informacion detras de login
- No datos personales: Solo datos de restaurantes, precios y fees
- User-Agents apropiados: Sin impersonation maliciosa
- Carga minima: Se bloquean recursos innecesarios (imagenes en listados)
- Uso limitado: Exclusivamente para analisis competitivo / fines de reclutamiento

> **Nota legal**: En un escenario de produccion, se recomienda consultar con el equipo
> legal antes de implementar scraping sistematico. Este ejercicio es para fines de evaluacion tecnica.

Ver [ETHICS.md](ETHICS.md) para el analisis completo.

## Tests

```bash
pytest tests/ -v    # 85 tests
```

Cobertura:
- Config: locations, products, helpers
- Data models: ScrapeResult, ProductResult, DeliveryInfo
- Parsers: parse_price, parse_time_range, fuzzy_match
- Integration: sample data generation, CSV consolidation
- Analysis: comparative, insights, visualizations

---

*Desarrollado como caso tecnico para el rol de AI Engineer en Rappi.*
