# Desk memecoins: escaneo automático (solo paper trading)
Corre 3 veces al día en GitHub Actions sin usar Claude. No opera, no usa claves privadas ni toca billeteras.
- `scripts/scan.py`: tokens recientes de Solana, BNB y Robinhood (GeckoTerminal + DexScreener).
- `scripts/filtro.py`: filtros numéricos 5.1 y bandas de edad.
- `scripts/reporte.py`: revisión de seguridad (`seguridad.py`) e informe en `escaneos/`.
- `scripts/sombra.py`: estudio en sombra; registra y mide a 24 h en `datos/estudio_reglas_sombra.tsv`.
Para correrlo a mano: pestaña Actions → "Escaneo desk (paper)" → Run workflow.

## Horarios (tope 1.000 min/mes de GitHub Actions)
- Escaneo: 3:47 AM, 9:07 AM, 12:27 PM* y 3:47 PM Bogotá (*se salta si el gasto del mes va por encima del ritmo).
- Reloj (watchlist Solana + H16): 1:07 AM, 3:47 AM, 9:07 AM, 12:27 PM y 3:47 PM.
- H16 historial: 1:23 AM, solo tokens nuevos o pendientes.
- Billeteras: diario, 3:17 AM.
- Freno (scripts/presupuesto.py): escaneos se cortan desde 950 min y el resto desde 985; abre un issue de aviso al pasar 800 y 950. Las corridas manuales siempre corren.
