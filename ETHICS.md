# Consideraciones Eticas de Scraping

## Principios

Este sistema fue disenado siguiendo practicas responsables de extraccion de datos publicos,
con el objetivo de minimizar el impacto en los servicios analizados y respetar los limites
tecnicos y legales aplicables.

## Medidas implementadas

### Rate limiting
- Delay de 3-5 segundos entre requests individuales (configurable en `config/settings.py`)
- Delay de 10-15 segundos entre ubicaciones
- Delay de 20-30 segundos entre plataformas
- Backoff exponencial en reintentos (1s, 2s, 4s, max 3 intentos)

### Anti-sobrecarga
- Bloqueo de recursos no necesarios (imagenes, fonts, media) en listados
- Maxima concurrencia: 1 plataforma a la vez (no paralelo agresivo)
- Playwright en modo headless con un solo contexto de browser

### Datos recolectados
- Exclusivamente datos visibles publicamente sin autenticacion
- Sin interaccion con flujos de checkout o pago
- Sin almacenamiento de datos de usuarios finales
- Solo precios, fees, tiempos y promociones de restaurantes

### Transparencia tecnica
- User-Agents reales de browsers comerciales (Chrome, Safari)
- Sin bypass de mecanismos de seguridad (CAPTCHAs, 2FA)
- Los screenshots son evidencia del estado de la UI, no se comparten

## Alcance y uso

Este sistema fue desarrollado como ejercicio tecnico de reclutamiento. Los datos generados:

- No se publican ni comercializan
- Se usan exclusivamente para el analisis presentado en este caso tecnico
- Se borran al finalizar el proceso de evaluacion

## Disclaimer

En un entorno de produccion real, se recomienda:

1. **Consultar con el equipo legal** antes de implementar scraping sistematico sobre
   plataformas de terceros
2. **Evaluar APIs oficiales**: verificar si Rappi, Uber Eats y DiDi Food ofrecen APIs
   de datos que puedan usarse en lugar de scraping
3. **Implementar acuerdos de datos**: si el scraping es para uso continuo, considerar
   acuerdos formales con las plataformas
4. **Revisar Terminos de Servicio**: los ToS de las plataformas pueden prohibir el scraping
   automatizado incluso de datos publicos
5. **Monitorear cambios legales**: el marco legal del scraping varia por jurisdiccion
   y evoluciona continuamente (ver hiQ Labs v. LinkedIn, 9th Circuit 2022)

## robots.txt verificados

| Plataforma | URL robots.txt | Notas |
|------------|----------------|-------|
| Rappi | rappi.com/robots.txt | Algunos paths de API desaconsejados |
| Uber Eats | ubereats.com/robots.txt | Crawlers de busqueda permitidos |
| DiDi Food | didi.com.mx/robots.txt | Mayormente permisivo para datos publicos |

> Este analisis de robots.txt es orientativo. La ausencia de restriccion en robots.txt
> no equivale a permiso legal para scraping a escala.
