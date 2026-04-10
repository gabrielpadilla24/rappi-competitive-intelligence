# Competitive Intelligence System for Rappi

Sistema automatizado de inteligencia competitiva que recolecta, analiza y visualiza datos de plataformas de delivery en México (Rappi, Uber Eats, DiDi Food) para generar insights accionables para equipos de Strategy y Pricing.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Tests](https://img.shields.io/badge/Tests-85%20passing-green)
![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red)
![Playwright](https://img.shields.io/badge/Scraping-Playwright-green)

---

## Tabla de Contenidos

- [Quick Start](#-quick-start)
- [Qué hace este sistema](#-qué-hace-este-sistema)
- [Arquitectura](#-arquitectura)
- [Cómo ejecutar](#-cómo-ejecutar)
- [Dashboard](#-dashboard)
- [Informe PDF](#-informe-pdf)
- [Datos Recolectados](#-datos-recolectados)
- [Stack Tecnológico](#-stack-tecnológico)
- [Desafíos Técnicos y Soluciones](#-desafíos-técnicos-y-soluciones)
- [Limitaciones Conocidas](#-limitaciones-conocidas)
- [Consideraciones Éticas](#-consideraciones-éticas)
- [Tests](#-tests)
- [Próximos Pasos](#-próximos-pasos)

---

## Quick Start

```bash
# 1. Clonar e instalar
git clone https://github.com/user/rappi-competitive-intelligence.git
cd rappi-competitive-intelligence
make setup

# 2. Opción A: Usar datos incluidos (no requiere browser)
# El repo incluye datos pre-scrapeados listos para análisis

# 3. Opción B: Generar datos sintéticos calibrados al mercado CDMX
make sample

# 4. Opción C: Scraping real (requiere Playwright + internet)
python run_scraper.py --platforms ubereats,rappi --mode quick --verbose

# 5. Ejecutar análisis completo
python -m analysis.comparative
python -m analysis.insights
python -m analysis.visualizations

# 6. Generar informe PDF
python generate_report.py --author "Tu Nombre"

# 7. Lanzar dashboard interactivo
make dashboard
```

---

## Qué hace este sistema

### Plataformas analizadas

| Plataforma | Método de scraping | Estado | Datos obtenidos |
|---|---|---|---|
| **Uber Eats** | Playwright + DOM parsing (`data-testid` selectors) | ✅ Funcional | Precios, ratings, reviews, tiempos, promotions. Rate limited después de ~6 requests consecutivos |
| **Rappi** | Playwright + network interception (API responses JSON) | ✅ Funcional (parcial) | Burger King: precios y tiempos. McDonald's: solo subcategoría "postres" disponible en búsqueda |
| **DiDi Food** | Playwright + login automático | ❌ Bloqueado | Web app requiere verificación SMS para acceso. Scraper implementado pero no ejecutable sin número mexicano |

### Métricas recolectadas

| Métrica | Uber Eats | Rappi | DiDi Food |
|---|---|---|---|
| Precio del producto | ✅ $99-$169 MXN | ✅ $209 MXN (Combo Whopper) | ❌ Requiere login |
| Delivery fee | ✅ $0 (envío gratis nuevos usuarios) | ✅ $0 (envío gratis) | ❌ |
| Service fee | ⚠️ No visible en página | ⚠️ No visible en página | ❌ |
| Tiempo de entrega | ✅ 14-48 min | ✅ 12 min | ❌ |
| Rating | ✅ 4.4-4.5 | ⚠️ No extraído | ❌ |
| Reviews | ✅ 7,000-15,000 | ⚠️ No extraído | ❌ |
| Promociones | ✅ 4-5 por restaurante | ⚠️ 0 encontradas | ❌ |
| Screenshots | ✅ Automáticos | ✅ Automáticos | ✅ (página de login) |

### Cobertura geográfica

- **25 direcciones** configuradas en CDMX (5 zonas socioeconómicas)
- **2 ciudades secundarias** (Guadalajara, Monterrey)
- **Datos reales obtenidos:** 5 ubicaciones en Uber Eats (Polanco, Santa Fe, Condesa, Del Valle Sur, Country Club) + 25 ubicaciones en Rappi (Burger King en todas)
- **Rate limiting de Uber Eats** impidió scraping completo de las 25 ubicaciones

### Outputs del sistema

1. **Datos crudos** — JSONs individuales por observación (`data/raw/`)
2. **CSV consolidado** — Dataset limpio para análisis (`data/processed/competitive_data.csv`)
3. **8 gráficos** de calidad presentación (`reports/charts/`)
4. **Top 5 Insights** accionables con Finding/Impact/Recommendation (`reports/top5_insights.json`)
5. **Dashboard interactivo** Streamlit con 6 tabs (`dashboard/app.py`)
6. **Informe ejecutivo PDF** de 13 páginas (`reports/competitive_report.pdf`)
7. **Screenshots** de evidencia por plataforma/ubicación (`data/screenshots/`)

---

## Arquitectura

```
rappi-competitive-intelligence/
├── config/                        # Configuración
│   ├── settings.py                #   Timeouts, delays, URLs, colores de marca
│   ├── locations.py               #   25 direcciones con lat/lng y metadata
│   └── products.py                #   7 productos de referencia + 3 restaurantes
├── scrapers/                      # Scrapers por plataforma
│   ├── base.py                    #   Clase abstracta + 5 data models normalizados
│   ├── ubereats_scraper.py        #   Playwright + DOM parsing
│   ├── rappi_scraper.py           #   Playwright + network interception
│   ├── didifood_scraper.py        #   Playwright + login automático
│   └── utils/                     #   Anti-detection, retry, screenshots, parsers
├── scripts/                       # Utilidades
│   ├── generate_sample_data.py    #   Datos sintéticos calibrados al mercado
│   └── consolidate_data.py        #   JSON → CSV consolidado
├── analysis/                      # Pipeline de análisis
│   ├── comparative.py             #   5 dimensiones comparativas
│   ├── insights.py                #   Top 5 insights accionables
│   └── visualizations.py          #   8 gráficos (matplotlib/seaborn)
├── dashboard/                     # Dashboard interactivo
│   ├── app.py                     #   Streamlit con 6 tabs (Plotly)
│   └── ai_summary.py             #   Resumen ejecutivo con Groq
├── data/
│   ├── raw/                       #   JSONs individuales por scrape
│   ├── processed/                 #   CSV consolidado
│   └── screenshots/               #   Evidencia visual organizada
├── reports/
│   ├── charts/                    #   8 gráficos PNG
│   ├── competitive_report.pdf     #   Informe ejecutivo (13 páginas)
│   ├── top5_insights.json         #   Insights en formato máquina
│   └── top5_insights.txt          #   Insights en formato legible
├── tests/                         # 85 tests (pytest)
├── run_scraper.py                 # CLI runner con argparse
├── generate_report.py             # Generador de PDF ejecutivo
├── Makefile                       # 12 targets
├── ETHICS.md                      # Consideraciones éticas
└── README.md
```

---

## Cómo ejecutar

### Scraping real (requiere Playwright)

```bash
# Instalar Playwright y browsers
make setup

# Scraping rápido — 6 ubicaciones prioritarias
python run_scraper.py --platforms ubereats,rappi --mode quick --verbose

# Scraping completo — 25 ubicaciones
python run_scraper.py --platforms ubereats,rappi --mode all --verbose

# Solo una plataforma
python run_scraper.py --platforms ubereats --locations polanco --verbose

# Solo una zona
python run_scraper.py --platforms rappi --zone-type high_income --verbose
```

### Datos sintéticos (sin browser)

```bash
# Genera datos calibrados al mercado CDMX
make sample              # 6 ubicaciones
make sample-all          # 25 ubicaciones

# Complementar datos reales con sintéticos
python -m scripts.generate_sample_data --all
python -m scripts.consolidate_data
```

### Pipeline de análisis

```bash
# Consolidar datos
python -m scripts.consolidate_data

# Análisis comparativo (genera CSVs + insights + gráficos)
python -m analysis.comparative
python -m analysis.insights
python -m analysis.visualizations

# Generar PDF ejecutivo
python generate_report.py --author "Gabriel Padilla"
```

### Pipeline completo con un comando

```bash
make demo    # setup + sample + analyze + report
```

---

## Dashboard

```bash
streamlit run dashboard/app.py
# → Abre en http://localhost:8501
```

**6 tabs interactivos:**

| Tab | Contenido |
|---|---|
| Executive Overview | KPIs, scorecard competitivo, radar chart, top 3 insights |
| Precios | Comparativa por producto/plataforma, tabla con deltas, drill-down por ubicación |
| Delivery & Fees | Stacked bar de costo total, fees comparativos, tiempos de entrega, fee como % |
| Geográfico | Heatmap por zona × plataforma, delta de precios, tabla detallada |
| Promociones | Tasa por plataforma, feed filtrable, distribución por tipo |
| AI Insights | Top 5 insights expandibles + resumen ejecutivo con Groq (opcional) |

**Sidebar global:** Filtros de plataforma, zona y restaurante que aplican a todas las tabs.

---

## Informe PDF

```bash
python generate_report.py --author "Gabriel Padilla"
# → reports/competitive_report.pdf (13 páginas, ~470 KB)
```

**Contenido:**
1. Portada con colores de marca
2. Resumen ejecutivo con métricas clave
3. Metodología (scope, direcciones, productos, stack, limitaciones)
4. Análisis comparativo de precios (gráficos + interpretación)
5. Análisis geográfico y tiempos de entrega
6. Estructura de fees y promociones
7. Top 5 Insights Accionables (Finding / Impact / Recommendation)
8. Scorecard competitivo multi-dimensión (radar chart)
9. Limitaciones y próximos pasos

Todos los textos y métricas son dinámicos — se regeneran automáticamente con datos nuevos.

---

## Datos Recolectados (Scraping Real)

### Uber Eats — Precios reales obtenidos

| Producto | Precio (MXN) | Restaurante | Ubicación |
|---|---|---|---|
| Big Mac (Home Office con Big Mac) | $99 | McDonald's Antara | Polanco, Condesa, Santa Fe, Del Valle Sur, Country Club |
| McTrío Big Mac mediano + McFlurry | $169 | McDonald's Antara | Mismas ubicaciones |
| McTrio mediano McNuggets 10 pzas | $129 | McDonald's Antara | Mismas ubicaciones |
| Combo Whopper + Pay o 4 Nuggets | $159 | Burger King (Antara) | Mismas ubicaciones |

- **Delivery fee:** $0 MXN (envío gratis para nuevos usuarios)
- **Tiempos:** 14-48 min (varía por ubicación)
- **Rating:** McDonald's 4.5★ (15,000 reviews), Burger King 4.4★ (7,000 reviews)
- **Promociones:** 5 activas por restaurante

### Rappi — Precios reales obtenidos

| Producto | Precio (MXN) | Restaurante | Ubicación |
|---|---|---|---|
| Combo Whopper | $209 | Burger King | 25 ubicaciones |

- **Delivery fee:** $0 MXN (envío gratis)
- **Tiempo:** 12 min
- **McDonald's:** Solo disponible como subcategoría "postres" en resultados de búsqueda

### Hallazgo clave de datos reales

**Combo Whopper en Rappi ($209) vs Uber Eats ($159) = +31% más caro en Rappi.** Este es un insight real del scraping que contradice la narrativa de "Rappi tiene precios más bajos" — al menos para Burger King, Uber Eats es significativamente más barato en precio de producto.

---

## Stack Tecnológico

| Componente | Herramienta | Justificación |
|---|---|---|
| Scraping | Playwright (Python) | Multi-browser, stealth mode, network interception, geolocation API |
| Anti-detection | UA rotation + random delays + geolocation | Evasión de bot detection sin proxies pagos |
| Datos | pandas, JSON, CSV | Stack estándar, flexible |
| Visualización estática | matplotlib, seaborn | Para PDF e imágenes de alta resolución |
| Visualización interactiva | Plotly | Para dashboard con hover, zoom, filtros |
| Dashboard | Streamlit | Python nativo, deployable, open source |
| PDF | fpdf2 | Ligero, sin dependencias externas |
| LLM (opcional) | Groq (Llama 3) | Resúmenes ejecutivos AI-powered |
| Testing | pytest (85 tests) | Config, data models, parsers, integración, análisis |

---

## Desafíos Técnicos y Soluciones

### 1. Rate Limiting de Uber Eats
**Problema:** Uber Eats bloquea después de ~6 requests consecutivos desde la misma IP. El address input desaparece y los search results retornan 0 cards.
**Solución implementada:** Random delays 3-6s, fallback URL approach, logging de failures.
**Solución en producción:** Proxies rotativos (Bright Data, ScraperAPI) + distribución de requests en ventanas de tiempo más amplias.

### 2. McDonald's en Rappi solo devuelve "Postres"
**Problema:** La búsqueda "McDonald's" en Rappi retorna solo "mcdonalds postres" (subcategoría sin Big Mac).
**Solución implementada:** Filtro de subcategorías (postres, desayunos, helados, pollos), warning claro en logs. Si solo hay subcategoría, procede pero documenta que los productos target no estarán disponibles.
**Causa raíz:** Rappi segmenta McDonald's en múltiples tiendas virtuales por categoría. La tienda principal no aparece en los resultados de búsqueda.

### 3. DiDi Food requiere verificación SMS
**Problema:** `didi-food.com/es-MX/food/` tiene web app con input de dirección, pero después redirige a login con verificación SMS (número mexicano + código de 6 dígitos).
**Solución implementada:** Scraper completo con login automático y persistencia de cookies. Detección de página de login con error descriptivo.
**Limitación:** No se puede automatizar la verificación SMS sin acceso a un teléfono mexicano.

### 4. Delivery Fee siempre $0
**Problema:** Tanto Uber Eats como Rappi muestran $0 de delivery fee (envío gratis).
**Análisis:** Ambas plataformas ofrecen envío gratis como promoción para nuevos usuarios o usuarios con membresía. El fee $0 es el valor real que ve un usuario nuevo.
**Implicación:** En producción, se necesitaría una cuenta sin promociones activas para ver el fee base real.

### 5. Parseo de precios incorrecto
**Bug:** "Elige 2 x $109" se parseaba como $2109. "2218-36 min" se parseaba como tiempo de entrega.
**Fix:** Regex más estrictos: `\$\s*(\d[\d,]*)` para precios con $, `\b(\d{1,3})\s*[–-]\s*(\d{1,3})` para tiempos con límite de 3 dígitos y word boundary.

### 6. Subcategorías de restaurantes
**Bug:** "Pollos de McDonald's Antara" y "mcdonalds postres" se matcheaban antes que "McDonald's Antara".
**Fix:** Lista de keywords de subcategorías + sort por `(is_subcategory, len(name))` para preferir el match principal.

### 7. Rappi no setea dirección
**Problema:** El address input no siempre aparece en rappi.com.mx.
**Fix:** `context.set_geolocation()` + `context.grant_permissions(["geolocation"])` antes de navegar. El browser reporta las coordenadas correctas cuando Rappi pide ubicación.

### 8. Rating y reviews no extraídos
**Bug:** Regex `\d\.\d` matcheaba precios (89.0) además de ratings (4.4).
**Fix:** Regex `(\d\.\d)\s*(?:[★*☆]|\()` que requiere estrella o paréntesis después del número.

---

## Limitaciones Conocidas

| Limitación | Impacto | Mitigación |
|---|---|---|
| **Uber Eats rate limiting** | Solo 5 de 25 ubicaciones scrapeadas | Datos complementados con sintéticos. En producción: proxies rotativos |
| **DiDi Food SMS** | 0 datos reales | Scraper implementado, limitación documentada. Requiere número mexicano |
| **Rappi McDonald's** | Solo subcategoría "postres" | Burger King funciona correctamente. McDonald's requiere navegación directa por URL |
| **Delivery fee $0** | No muestra fee base real | Ambas plataformas ofrecen envío gratis para nuevos usuarios |
| **Service fee** | No visible en página del restaurante | Solo visible durante checkout. Documentado como limitación |
| **Snapshot temporal** | Datos de un momento puntual | En producción: cron diario para tendencias |
| **Precios dinámicos** | Varían por hora y demanda | Múltiples corridas en diferentes horarios |
| **Geolocation vs address input** | Rappi no siempre respeta geolocation | El address input no aparece consistentemente |

---

## Consideraciones Éticas

Este sistema fue diseñado con prácticas responsables de scraping:

- ✅ **Rate limiting:** 3-6 segundos entre requests, 8-12 segundos entre restaurantes
- ✅ **Solo datos públicos:** Precios, fees y tiempos visibles para cualquier usuario
- ✅ **No datos personales:** Solo datos de restaurantes y productos
- ✅ **User-Agents apropiados:** Rotación de UAs reales, sin impersonation maliciosa
- ✅ **Carga mínima:** Bloqueo de recursos innecesarios en listados
- ✅ **Documentación transparente:** Todas las limitaciones documentadas
- ✅ **Código reproducible:** Instrucciones completas en README

> **Nota legal:** Este proyecto fue desarrollado como ejercicio técnico para fines de reclutamiento. En un escenario de producción, se recomienda consultar con Legal, considerar APIs oficiales, y establecer acuerdos de uso de datos.

Ver [ETHICS.md](ETHICS.md) para más detalle.

---

## Tests

```bash
pytest tests/ -v    # 85 tests
```

| Suite | Tests | Cobertura |
|---|---|---|
| Config (locations, products) | 10 | Coordenadas, prioridades, helpers |
| Data models | 6 | ScrapeResult, ProductResult, DeliveryInfo |
| Parsers | 18 | parse_price, parse_time_range, fuzzy_match |
| Integration | 19 | Sample data, CSV consolidation, pipeline |
| Analysis | 27 | Comparative, insights, visualizations |
| Scrapers | 5 | Base scraper, factory |

---

## Próximos Pasos (Producción)

1. **Proxies rotativos:** Bright Data o ScraperAPI para evitar rate limiting de Uber Eats
2. **GitHub Actions:** Cron diario para capturar tendencias temporales
3. **Más ciudades:** Guadalajara, Monterrey, Puebla, Cancún
4. **Más verticales:** Retail (OXXO, supermercados), Farmacia
5. **DiDi Food:** Servicio de SMS virtual o API no oficial para resolver autenticación
6. **Datos internos:** Correlacionar con pedidos, GMV y retención de Rappi
7. **Alertas:** Slack/email cuando la competencia cambia precios o fees
8. **ML:** Predicción de movimientos de precios de la competencia

---



**Autor:** Gabriel Padilla
