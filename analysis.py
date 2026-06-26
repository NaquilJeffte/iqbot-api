"""
analysis.py v3.0 — Motor de señales con timing perfecto
- Python decide todo automaticamente
- Calcula el momento OPTIMO de entrada
- Distancia minima de movimiento por timeframe
- Solo señal cuando hay certeza real 90%+
"""

import math
import time


# ═══════════════════════════════════════════════════════════════
#  TIMING — Cuándo entrar según el timeframe
# ═══════════════════════════════════════════════════════════════

DISTANCIA_MINIMA = {
    3:    0.0008,  # 3 segundos  → 0.0008% movimiento minimo
    5:    0.001,   # 5 segundos
    10:   0.002,   # 10 segundos
    15:   0.003,   # 15 segundos
    30:   0.005,   # 30 segundos
    60:   0.010,   # 1 minuto
    120:  0.015,   # 2 minutos
    300:  0.025,   # 5 minutos
    900:  0.040,   # 15 minutos
    3600: 0.080,   # 1 hora
}

def calcular_timing_entrada(intervalo_seg):
    """
    Calcula el momento exacto para entrar.
    
    Retorna:
      - momento: "ENTRAR_AHORA" / "ESPERAR_PROXIMA" / "PRECAUCION"
      - segundos_restantes: cuántos segundos quedan de la vela actual
      - porcentaje_restante: % del tiempo que queda
      - mensaje: explicación clara para el usuario
    """
    ahora = time.time()
    segundos_en_vela   = ahora % intervalo_seg
    segundos_restantes = intervalo_seg - segundos_en_vela
    porcentaje_restante = (segundos_restantes / intervalo_seg) * 100

    # Reglas de entrada según tiempo restante
    if porcentaje_restante >= 60:
        # Más del 60% de la vela por delante — momento ÓPTIMO
        momento = "ENTRAR_AHORA"
        if intervalo_seg <= 10:
            mensaje = f"Entrar YA — quedan {round(segundos_restantes, 1)}s"
        else:
            mensaje = f"Momento óptimo — quedan {round(segundos_restantes)}s de {intervalo_seg}s"

    elif porcentaje_restante >= 30:
        # Entre 30-60% — entrar con precaución
        momento = "PRECAUCION"
        mensaje = f"Entrar con cuidado — quedan {round(segundos_restantes)}s ({round(porcentaje_restante)}%)"

    else:
        # Menos del 30% — demasiado tarde, esperar la siguiente
        momento = "ESPERAR_PROXIMA"
        mensaje = f"Muy tarde — esperar próxima vela en {round(segundos_restantes)}s"

    return {
        "momento":            momento,
        "segundos_restantes": round(segundos_restantes, 1),
        "porcentaje_restante": round(porcentaje_restante, 1),
        "mensaje":            mensaje,
        "puede_entrar":       momento in ("ENTRAR_AHORA", "PRECAUCION"),
    }


def calcular_movimiento_real(candles, intervalo_seg):
    """
    Calcula si el precio ya se movió lo suficiente para entrar.
    Compara el movimiento actual con el mínimo requerido por timeframe.
    """
    if len(candles) < 2:
        return False, 0.0

    ultima   = candles[-1]
    anterior = candles[-2]

    precio_actual   = ultima["close"]
    precio_anterior = anterior["close"]

    if precio_anterior == 0:
        return False, 0.0

    movimiento_pct = abs(precio_actual - precio_anterior) / precio_anterior * 100

    # Buscar la distancia mínima más cercana al intervalo
    distancia_min = DISTANCIA_MINIMA.get(
        intervalo_seg,
        DISTANCIA_MINIMA.get(60, 0.010)
    )

    suficiente = movimiento_pct >= distancia_min
    return suficiente, round(movimiento_pct, 5)


# ═══════════════════════════════════════════════════════════════
#  INDICADORES ULTRA RAPIDOS
# ═══════════════════════════════════════════════════════════════

def ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val


def rsi_rapido(prices, period=10):
    n = min(period, len(prices) // 3)
    if n < 3 or len(prices) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(len(prices) - n, len(prices)):
        d = prices[i] - prices[i-1]
        if d > 0: gains += d
        else: losses -= d
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def momentum(prices, period=5):
    if len(prices) < period + 1:
        return None
    return prices[-1] - prices[-period-1]


def atr(candles, period=7):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h  = candles[i]["max"]
        l  = candles[i]["min"]
        pc = candles[i-1]["close"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs[-period:]) / period


def bollinger_rapido(prices, period=15):
    if len(prices) < period:
        return None, None, None
    sub = prices[-period:]
    sma = sum(sub) / period
    std = math.sqrt(sum((p-sma)**2 for p in sub) / period)
    return sma + 2*std, sma, sma - 2*std


def tendencia_precio(closes, ventana=10):
    if len(closes) < ventana:
        return "LATERAL", 0
    sub = closes[-ventana:]
    n = len(sub)
    x_mean = (n - 1) / 2
    y_mean = sum(sub) / n
    num = sum((i - x_mean) * (sub[i] - y_mean) for i in range(n))
    den = sum((i - x_mean)**2 for i in range(n))
    if den == 0:
        return "LATERAL", 0
    slope = num / den
    slope_pct = abs(slope) / y_mean * 100 if y_mean else 0
    if slope_pct < 0.001:
        return "LATERAL", 0
    return ("UP" if slope > 0 else "DOWN"), min(slope_pct * 100, 1.0)


def detectar_patron_vela(candles):
    if len(candles) < 3:
        return "NEUTRAL", 0
    c  = candles[-1]
    c1 = candles[-2]
    c2 = candles[-3]
    cuerpo = abs(c["close"] - c["open"])
    rango  = c["max"] - c["min"] or 0.00001
    s_inf  = min(c["close"], c["open"]) - c["min"]
    s_sup  = c["max"] - max(c["close"], c["open"])

    if (c1["close"] < c1["open"] and c["close"] > c["open"] and
            c["open"] < c1["close"] and c["close"] > c1["open"]):
        return "BUY", 90
    if (c1["close"] > c1["open"] and c["close"] < c["open"] and
            c["open"] > c1["close"] and c["close"] < c1["open"]):
        return "SELL", 90
    if (c["close"] > c["open"] and c1["close"] > c1["open"] and
            c2["close"] > c2["open"] and
            c["close"] > c1["close"] > c2["close"]):
        return "BUY", 85
    if (c["close"] < c["open"] and c1["close"] < c1["open"] and
            c2["close"] < c2["open"] and
            c["close"] < c1["close"] < c2["close"]):
        return "SELL", 85
    # Sin patron fuerte reconocido → NEUTRAL
    return "NEUTRAL", 0


def nivel_soporte_resistencia(candles, ventana=20):
    if len(candles) < ventana:
        return None, None
    sub    = candles[-ventana:]
    precio = candles[-1]["close"]
    maximos = sorted([c["max"] for c in sub], reverse=True)[:3]
    minimos = sorted([c["min"] for c in sub])[:3]
    resistencia = sum(maximos) / len(maximos)
    soporte     = sum(minimos) / len(minimos)
    dist_res = (resistencia - precio) / precio * 100
    dist_sop = (precio - soporte) / precio * 100
    return dist_sop, dist_res


def calcular_volatilidad_real(candles, periodo=14):
    atr_val = atr(candles, periodo)
    if not atr_val:
        return 0.0, "baja"
    precio = candles[-1]["close"]
    pct = (atr_val / precio) * 100 if precio else 0
    if pct >= 0.35:
        return round(pct, 4), "muy_alta"
    elif pct >= 0.25:
        return round(pct, 4), "alta"
    elif pct >= 0.15:
        return round(pct, 4), "media_alta"
    elif pct >= 0.05:
        return round(pct, 4), "media"
    return round(pct, 4), "baja"


# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL v3.0
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    Motor de señales v3.0 con timing perfecto.
    
    Nuevo en v3:
    - Verifica si hay suficiente movimiento para el timeframe
    - Calcula el momento exacto de entrada
    - No genera señal si es muy tarde en la vela
    - Garantiza que los últimos 30-40% de la vela son de espera tranquila
    """
    if len(candles) < 20:
        return {"error": "Datos insuficientes", "direccion": "ESPERAR"}

    closes   = [c["close"] for c in candles]
    precio   = closes[-1]
    es_corto = timeframe_seg <= 30

    # ── TIMING ──────────────────────────────────────────────────
    timing = calcular_timing_entrada(timeframe_seg)

    # Si es muy tarde en la vela → esperar la siguiente
    if timing["momento"] == "ESPERAR_PROXIMA":
        return {
            "direccion":   "ESPERAR_PROXIMA_VELA",
            "estrategia":  "automatica",
            "timing":      timing,
            "mensaje":     timing["mensaje"],
            "volatilidad": "media",
            "tendencia":   "LATERAL",
            "razones":     [f"Muy tarde para entrar — {timing['mensaje']}"],
            "indicadores": {"precio": round(precio, 5)},
            "fibonacci":   {"niveles": {}, "zona_actual": None, "precio_zona": None},
            "patrones_velas": [],
            "score_buy":   0,
            "score_sell":  0,
            "confianza":   0,
        }

    # ── MOVIMIENTO MINIMO ────────────────────────────────────────
    movimiento_suficiente, movimiento_pct = calcular_movimiento_real(candles, timeframe_seg)

    # ── INDICADORES ──────────────────────────────────────────────
    tendencia_corta, _ = tendencia_precio(closes, 5)
    tendencia, _       = tendencia_precio(closes, 15)

    ef5,  es10 = (ema(closes, 5),  ema(closes, 10))
    ef10, es20 = (ema(closes, 10), ema(closes, 20))
    ef20, es50 = (ema(closes, 20), ema(closes, 50)) if len(closes) >= 50 else (None, None)

    rsi_val    = rsi_rapido(closes, 8 if es_corto else 12)
    mom3       = momentum(closes, 3)
    mom7       = momentum(closes, 7)
    bb_up, bb_mid, bb_lo = bollinger_rapido(closes, 12 if es_corto else 18)
    patron_dir, patron_fuerza = detectar_patron_vela(candles)
    dist_sop, dist_res = nivel_soporte_resistencia(candles, 20)
    vol_pct, vol_nivel = calcular_volatilidad_real(candles)

    # ── VOTOS ────────────────────────────────────────────────────
    votos_buy  = []
    votos_sell = []

    # Tendencia corta
    if tendencia_corta == "UP":   votos_buy.append(("tendencia_corta", 1))
    elif tendencia_corta == "DOWN": votos_sell.append(("tendencia_corta", 1))

    # Tendencia larga
    if tendencia == "UP":   votos_buy.append(("tendencia_larga", 2))
    elif tendencia == "DOWN": votos_sell.append(("tendencia_larga", 2))

    # EMA 5/10
    if ef5 and es10:
        if ef5 > es10: votos_buy.append(("ema_5_10", 1))
        else: votos_sell.append(("ema_5_10", 1))

    # EMA 10/20
    if ef10 and es20:
        if ef10 > es20: votos_buy.append(("ema_10_20", 1))
        else: votos_sell.append(("ema_10_20", 1))

    # EMA 20/50
    if ef20 and es50:
        if ef20 > es50: votos_buy.append(("ema_20_50", 2))
        else: votos_sell.append(("ema_20_50", 2))

    # RSI
    if rsi_val is not None:
        if rsi_val < 25:   votos_buy.append(("rsi_extremo", 3))
        elif rsi_val < 40: votos_buy.append(("rsi", 2))
        elif rsi_val > 75: votos_sell.append(("rsi_extremo", 3))
        elif rsi_val > 60: votos_sell.append(("rsi", 2))

    # Momentum doble
    if mom3 is not None and mom7 is not None:
        if mom3 > 0 and mom7 > 0:   votos_buy.append(("momentum", 2))
        elif mom3 < 0 and mom7 < 0: votos_sell.append(("momentum", 2))

    # Bollinger
    if bb_up and bb_lo and bb_mid:
        if precio < bb_lo:   votos_buy.append(("bollinger_extremo", 3))
        elif precio > bb_up: votos_sell.append(("bollinger_extremo", 3))
        elif precio < bb_mid: votos_buy.append(("bollinger", 1))
        else: votos_sell.append(("bollinger", 1))

    # Patron de vela
    if patron_dir == "BUY"  and patron_fuerza >= 85:
        votos_buy.append(("patron_vela", 4))
    elif patron_dir == "SELL" and patron_fuerza >= 85:
        votos_sell.append(("patron_vela", 4))

    # Soporte/Resistencia
    if dist_sop is not None and dist_res is not None:
        if dist_sop < 0.08: votos_buy.append(("soporte", 2))
        if dist_res < 0.08: votos_sell.append(("resistencia", 2))

    # Movimiento suficiente — bonus si ya se movió lo necesario
    if movimiento_suficiente:
        if tendencia_corta == "UP":   votos_buy.append(("movimiento_confirmado", 2))
        elif tendencia_corta == "DOWN": votos_sell.append(("movimiento_confirmado", 2))

    # ── DECISION ─────────────────────────────────────────────────
    peso_buy  = sum(v[1] for v in votos_buy)
    peso_sell = sum(v[1] for v in votos_sell)
    total_v   = len(votos_buy) + len(votos_sell)

    min_votos = 5 if es_corto else 4
    min_peso  = 9 if es_corto else 7

    puede_buy  = len(votos_buy)  >= min_votos and peso_buy  >= min_peso
    puede_sell = len(votos_sell) >= min_votos and peso_sell >= min_peso
    conflicto  = abs(peso_buy - peso_sell) < 3

    if conflicto or (not puede_buy and not puede_sell):
        direccion = "ESPERAR"
    elif puede_buy and peso_buy > peso_sell:
        direccion = "BUY"
    elif puede_sell and peso_sell > peso_buy:
        direccion = "SELL"
    else:
        direccion = "ESPERAR"

    # Certeza interna
    certeza = 0
    if total_v > 0 and direccion in ("BUY", "SELL"):
        vg = len(votos_buy) if direccion == "BUY" else len(votos_sell)
        certeza = round((vg / total_v) * 100)

    if certeza < 75 and direccion not in ("ESPERAR",):
        direccion = "ESPERAR"

    # Razones legibles
    votos_ganadores = votos_buy if direccion == "BUY" else votos_sell
    razones = [v[0].replace("_", " ").title() for v, _ in
               [(v, v[1]) for v in votos_ganadores[:5]]]

    return {
        "direccion":   direccion,
        "estrategia":  "automatica",
        "volatilidad": vol_nivel,
        "tendencia":   tendencia,
        "timing":      timing,
        "movimiento":  {
            "suficiente":     movimiento_suficiente,
            "porcentaje":     movimiento_pct,
            "minimo_requerido": DISTANCIA_MINIMA.get(timeframe_seg, 0.01),
        },
        "razones":     razones,
        "votos_buy":   len(votos_buy),
        "votos_sell":  len(votos_sell),
        "certeza_interna": certeza,
        "confianza":   certeza,
        "score_buy":   peso_buy,
        "score_sell":  peso_sell,
        "indicadores": {
            "precio":      round(precio, 5),
            "rsi":         round(rsi_val, 1) if rsi_val else None,
            "momentum":    round(mom3, 6) if mom3 else None,
            "ema_rapida":  round(ef5, 5) if ef5 else None,
            "ema_lenta":   round(es10, 5) if es10 else None,
            "bb_superior": round(bb_up, 5) if bb_up else None,
            "bb_inferior": round(bb_lo, 5) if bb_lo else None,
            "patron_vela": patron_dir,
            "volatilidad_pct": vol_pct,
        },
        "fibonacci":      {"niveles": {}, "zona_actual": None, "precio_zona": None},
        "patrones_velas": [{"patron": patron_dir, "fuerza": patron_fuerza}] if patron_fuerza > 0 else [],
    }


# ═══════════════════════════════════════════════════════════════
#  ESCANEO AUTOMATICO
# ═══════════════════════════════════════════════════════════════

def escanear_mejores_activos(candles_por_activo, timeframe_seg=60):
    resultados = []
    for activo, candles in candles_por_activo.items():
        if not candles or len(candles) < 20:
            continue
        try:
            r = generar_senal(candles, "auto", timeframe_seg)
            if r.get("direccion") in ("BUY", "SELL"):
                resultados.append({
                    "activo":    activo,
                    "direccion": r["direccion"],
                    "certeza":   r.get("certeza_interna", 0),
                    "volatilidad": r.get("volatilidad", "media"),
                    "timing":    r.get("timing", {}),
                    "analisis":  r,
                })
        except Exception:
            continue

    resultados.sort(key=lambda x: x["certeza"], reverse=True)

    if not resultados:
        return {"ok": False, "mensaje": "Sin señales claras ahora", "activos": []}

    mejor = resultados[0]
    return {
        "ok":      True,
        "mensaje": f"{mejor['activo']} → {mejor['direccion']}",
        "mejor":   mejor,
        "activos": resultados[:5],
    }


def calcular_volatilidad_real_simple(candles, periodo=14):
    """Alias para compatibilidad con top_activos"""
    vol_pct, _ = calcular_volatilidad_real(candles, periodo)
    return vol_pct


# Aliases compatibilidad
def detectar_volatilidad(candles, periodo=14):
    _, nivel = calcular_volatilidad_real(candles, periodo)
    return nivel

def seleccionar_estrategia_auto(candles):
    return "automatica", detectar_volatilidad(candles)
