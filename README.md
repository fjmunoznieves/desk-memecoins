# Desk memecoins: escaneo automático (solo paper trading)
Corre 3 veces al día en GitHub Actions sin usar Claude. No opera, no usa claves privadas ni toca billeteras.
- `scripts/scan.py`: tokens recientes de Solana, BNB y Robinhood (GeckoTerminal + DexScreener).
- `scripts/filtro.py`: filtros numéricos 5.1 y bandas de edad.
- `scripts/reporte.py`: revisión de seguridad (`seguridad.py`) e informe en `escaneos/`.
- `scripts/sombra.py`: estudio en sombra; registra y mide a 24 h en `datos/estudio_reglas_sombra.tsv`.
Para correrlo a mano: pestaña Actions → "Escaneo desk (paper)" → Run workflow.
