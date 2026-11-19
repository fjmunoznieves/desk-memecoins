CREATE TABLE IF NOT EXISTS det (mint TEXT PRIMARY KEY, billetera TEXT, ts_tx INTEGER, ts_det INTEGER, firma TEXT, fuente TEXT, sym TEXT, precio TEXT, mc INTEGER, liq INTEGER, pool TEXT, creado INTEGER);
CREATE INDEX IF NOT EXISTS det_ts ON det(ts_det);
CREATE TABLE IF NOT EXISTS muestra (id INTEGER PRIMARY KEY, ts INTEGER, cuerpo TEXT);
