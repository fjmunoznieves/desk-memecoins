# Desk memecoins: escaneo automático (solo paper trading)
Corre 3 veces al día en GitHub Actions sin usar Claude. No opera, no usa claves privadas ni toca billeteras.
- `scripts/scan.py`: tokens recientes de Solana, BNB y Robinhood (GeckoTerminal + DexScreener).
- `scripts/filtro.py`: filtros numéricos 5.1 y bandas de edad.
- `scripts/reporte.py`: revisión de seguridad (`seguridad.py`) e informe en `escaneos/`.
- `scripts/sombra.py`: estudio en sombra; registra y mide a 24 h en `datos/estudio_reglas_sombra.tsv`.
Para correrlo a mano: pestaña Actions → "Escaneo desk (paper)" → Run workflow.

## Horarios (tope 1.000 min/mes de GitHub Actions, horario de operación 4 AM–6 PM Bogotá)
- Escaneo: 3:47, 7:07*, 10:27 AM, 1:47 PM* y 5:07 PM (*opcionales: se saltan si el gasto del mes va por encima del ritmo).
- Reloj (watchlist Solana + H16): 1:07, 4:07, 6:37, 9:07, 11:37 AM, 2:07 y 4:37 PM.
- H16 historial: 1:23 AM, solo tokens nuevos o pendientes.
- Billeteras: cada 2 días, 7:17 AM.
- Freno: scripts/presupuesto.py suma los minutos del mes; escaneos se cortan desde 950 y el resto desde 985. Las corridas manuales siempre corren.
