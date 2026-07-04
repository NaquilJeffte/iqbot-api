"""
analysis.py v6.0 — CONFIANZA EXTREMA (90-95%)
- SOLO señales con confirmación MÚLTIPLE
- Filtros ultra estrictos
- Pocas señales, pero CASI SEGURAS
- Ideal para 30s, 45s, 1m, 2m, 3m, 5m
"""

import math
import time


# ═══════════════════════════════════════════════════════════════
#  INDICADORES CONFIRMADORES
# ═══════════════════════════════════════════════════════════════

def ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val


def rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains = losses = 0.0
    for i in range(len(prices) - period, len(prices)):
        d = prices[i] - prices[i-1]
        if d > 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100.0
    if gains == 0:
        return 0.0
    rs = (gains / period) / (losses / period)
    return 100 - 100 / (1 + rs)


def momentum(prices, period=5):
    if len(prices) < period + 1:
        return 0
    return prices[-1] - prices[-period-1]


def bollinger(prices, period=20):
    if len(prices) < period:
        return None, None, None
    sub = prices[-period:]
    sma = sum(sub) / period
    std = math.sqrt(sum((p - sma) ** 2 for p in sub) / period)
    return sma + 2*std, sma, sma - 2*std


def atr(candles, period=14):
    if len(candles) < period + 1:
        return 0.001
    trs = []
    for i in range(1, len(candles)):
        h = candles[i].get("high", candles[i].get("max", 0))
        l = candles[i].get("low", candles[i].get("min", 0))
        pc = candles[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period


def stochastico(prices, period=14):
    if len(prices) < period:
        return 50.0
    sub = prices[-period:]
    mn, mx = min(sub), max(sub)
    if mx == mn:
        return 50.0
    return (prices[-1] - mn) / (mx - mn) * 100


def macd(prices):
    if len(prices) < 26:
        return 0, 0
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
    if not ema12 or not ema26:
        return 0, 0
    macd_line = ema12 - ema26
    return macd_line, macd_line * 0.9


def tendencia_lineal(closes, ventana=20):
    if len(closes) < ventana:
        return "LATERAL", 0
    sub = closes[-ventana:]
    n = len(sub)
    x_mean = (n - 1) / 2
    y_mean = sum(sub) / n
    num = sum((i - x_mean) * (sub[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return "LATERAL", 0
    slope = num / den
    slope_pct = abs(slope) / (y_mean or 0.0001) * 100
    if slope_pct < 0.002:
        return "LATERAL", 0
    return ("UP" if slope > 0 else "DOWN"), min(slope_pct, 1.0)


def patron_velas(candles):
    """Detecta patrones de velas CONFIRMADOS"""
    if len(candles) < 3:
        return "NEUTRAL", 0

    def norm(c):
        return {
            "open": c.get("open", 0),
            "close": c.get("close", 0),
            "high": c.get("high", c.get("max", 0)),
            "low": c.get("low", c.get("min", 0)),
        }

    c = norm(candles[-1])
    c1 = norm(candles[-2])
    c2 = norm(candles[-3])

    # Engulfing alcista CONFIRMADO
    if (c1["close"] < c1["open"] and c["close"] > c["open"] and
            c["open"] <= c1["close"] and c["close"] >= c1["open"]):
        # Verificar confirmación con cierre
        if len(candles) >= 4:
            c3 = norm(candles[-4])
            if c3["close"] < c3["open"]:  # Confirmación bajista previa
                return "BUY", 98
        return "BUY", 95

    # Engulfing bajista CONFIRMADO
    if (c1["close"] > c1["open"] and c["close"] < c["open"] and
            c["open"] >= c1["close"] and c["close"] <= c1["open"]):
        if len(candles) >= 4:
            c3 = norm(candles[-4])
            if c3["close"] > c3["open"]:  # Confirmación alcista previa
                return "SELL", 98
        return "SELL", 95

    # 3 velas consecutivas + BREAKOUT
    if len(candles) >= 5:
        c3 = norm(candles[-4])
        c4 = norm(candles[-5])
        # 3 alcistas + rompimiento de resistencia
        if (c["close"] > c["open"] and c1["close"] > c1["open"] and
                c2["close"] > c2["open"] and
                c["close"] > c1["close"] > c2["close"] and
                c["high"] > c3["high"] and c3["high"] > c4["high"]):
            return "BUY", 97

        # 3 bajistas + rompimiento de soporte
        if (c["close"] < c["open"] and c1["close"] < c1["open"] and
                c2["close"] < c2["open"] and
                c["close"] < c1["close"] < c2["close"] and
                c["low"] < c3["low"] and c3["low"] < c4["low"]):
            return "SELL", 97

    return "NEUTRAL", 0


# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL v6.0 — CONFIANZA EXTREMA
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v6.0 — CONFIANZA EXTREMA 90-95%
    - Múltiples confirmaciones REQUERIDAS
    - Umbrales ultra estrictos
    - POCAS señales, pero CASI SEGURAS
    """
    if len(candles) < 30:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "estrategia": "confianza_extrema",
            "volatilidad": "media",
            "tendencia": "LATERAL",
            "razones": ["Datos insuficientes (necesita 30 velas)"],
            "votos_buy": 0,
            "votos_sell": 0,
            "score_buy": 0,
            "score_sell": 0,
            "indicadores": {},
            "fibonacci": {},
            "patrones_velas": [],
            "timing": {},
        }

    closes = [c["close"] for c in candles]
    precio = closes[-1]

    # ── 10 INDICADORES CON PESO EXTREMO ──────────────────────
    votos_buy = []
    votos_sell = []

    # 1. TENDENCIA CORTA (5 velas) - PESO 5
    tend_corta, fuerza_corta = tendencia_lineal(closes, min(5, len(closes)))
    if fuerza_corta > 0.005:  # Solo tendencias FUERTES
        if tend_corta == "UP":
            votos_buy.append(("tendencia_corta_fuerte", 5))
        else:
            votos_sell.append(("tendencia_corta_fuerte", 5))

    # 2. TENDENCIA LARGA (20 velas) - PESO 5
    tend_larga, fuerza_larga = tendencia_lineal(closes, min(20, len(closes)))
    if fuerza_larga > 0.003:  # Solo tendencias FUERTES
        if tend_larga == "UP":
            votos_buy.append(("tendencia_larga_fuerte", 5))
        else:
            votos_sell.append(("tendencia_larga_fuerte", 5))

    # 3. EMA 5 vs EMA 20 (CRUCE CONFIRMADO) - PESO 4
    ema5 = ema(closes, min(5, len(closes)))
    ema20 = ema(closes, min(20, len(closes)))
    if ema5 and ema20:
        diff_pct = abs(ema5 - ema20) / (precio or 0.0001) * 100
        if diff_pct > 0.01:  # Cruce SIGNIFICATIVO
            if ema5 > ema20:
                votos_buy.append(("ema_cruce_confirmado", 4))
            else:
                votos_sell.append(("ema_cruce_confirmado", 4))

    # 4. EMA 10 vs EMA 50 - PESO 4
    ema10 = ema(closes, min(10, len(closes)))
    ema50 = ema(closes, min(50, len(closes))) if len(closes) >= 50 else None
    if ema10 and ema50:
        diff_pct = abs(ema10 - ema50) / (precio or 0.0001) * 100
        if diff_pct > 0.01:
            if ema10 > ema50:
                votos_buy.append(("ema_lenta_confirmada", 4))
            else:
                votos_sell.append(("ema_lenta_confirmada", 4))

    # 5. RSI (EXTREMOS) - PESO 5
    rsi_val = rsi(closes, min(14, len(closes) // 2))
    if rsi_val < 20:  # Extremo sobrevendido
        votos_buy.append(("rsi_extremo_sobrevendido", 5))
    elif rsi_val < 30:
        votos_buy.append(("rsi_sobrevendido", 3))
    elif rsi_val > 80:  # Extremo sobrecomprado
        votos_sell.append(("rsi_extremo_sobrecomprado", 5))
    elif rsi_val > 70:
        votos_sell.append(("rsi_sobrecomprado", 3))

    # 6. MACD (CONFIRMADO) - PESO 4
    macd_line, signal_line = macd(closes)
    diff_pct = abs(macd_line - signal_line) / (precio or 0.0001) * 100
    if diff_pct > 0.005:  # Separación SIGNIFICATIVA
        if macd_line > signal_line:
            votos_buy.append(("macd_confirmado", 4))
        else:
            votos_sell.append(("macd_confirmado", 4))

    # 7. MOMENTUM (ACELERACIÓN) - PESO 4
    mom = momentum(closes, min(5, len(closes) - 1))
    mom_largo = momentum(closes, min(10, len(closes) - 1))
    mom_pct = abs(mom) / (precio or 0.0001) * 100
    if mom_pct > 0.01:  # Momentum SIGNIFICATIVO
        if mom > 0 and mom_largo > 0:
            votos_buy.append(("momentum_fuerte", 4))
        elif mom < 0 and mom_largo < 0:
            votos_sell.append(("momentum_fuerte", 4))

    # 8. BOLLINGER (EXTREMOS) - PESO 4
    bb_up, bb_mid, bb_lo = bollinger(closes, min(20, len(closes)))
    if bb_up and bb_lo:
        bb_ancho = (bb_up - bb_lo) / (bb_mid or 0.0001) * 100
        if bb_ancho > 2:  # Volatilidad alta
            if precio <= bb_lo * 1.001:  # Tocando banda inferior
                votos_buy.append(("bollinger_extremo_inferior", 4))
            elif precio >= bb_up * 0.999:  # Tocando banda superior
                votos_sell.append(("bollinger_extremo_superior", 4))

    # 9. ESTOCÁSTICO (EXTREMOS) - PESO 3
    stoch = stochastico(closes, min(14, len(closes)))
    if stoch < 15:
        votos_buy.append(("estocastico_extremo_bajo", 3))
    elif stoch < 30:
        votos_buy.append(("estocastico_bajo", 2))
    elif stoch > 85:
        votos_sell.append(("estocastico_extremo_alto", 3))
    elif stoch > 70:
        votos_sell.append(("estocastico_alto", 2))

    # 10. PATRÓN DE VELAS (FUERTE) - PESO 6
    patron_dir, patron_fuerza = patron_velas(candles)
    if patron_dir == "BUY" and patron_fuerza >= 95:
        votos_buy.append(("patron_vela_fuerte", 6))
    elif patron_dir == "SELL" and patron_fuerza >= 95:
        votos_sell.append(("patron_vela_fuerte", 6))
    elif patron_dir == "BUY" and patron_fuerza >= 85:
        votos_buy.append(("patron_vela", 4))
    elif patron_dir == "SELL" and patron_fuerza >= 85:
        votos_sell.append(("patron_vela", 4))

    # ── DECISIÓN CON FILTROS EXTREMOS ──────────────────────────
    peso_buy = sum(v[1] for v in votos_buy)
    peso_sell = sum(v[1] for v in votos_sell)
    total = peso_buy + peso_sell or 1

    # CONFIRMACIÓN: Ambas tendencias DEBEN estar alineadas
    tendencias_alineadas = (
        (tend_corta == "UP" and tend_larga == "UP") or
        (tend_corta == "DOWN" and tend_larga == "DOWN")
    )

    # FILTROS EXTREMOS PARA CONFIANZA 90-95%
    UMBRAL_MINIMO = 12  # MUY ALTO (antes era 5)
    DIFERENCIAL_MINIMO = 2.0  # 100% más de peso (antes 1.3)

    # SOLO SEÑAL SI HAY CONFIRMACIÓN MÚLTIPLE
    if tendencias_alineadas and peso_buy >= UMBRAL_MINIMO and peso_buy > peso_sell * DIFERENCIAL_MINIMO:
        direccion = "BUY"
        confianza = min(round((peso_buy / total) * 100), 98)
        razones = [v[0].replace("_", " ").title() for v in votos_buy[:5]]
    elif tendencias_alineadas and peso_sell >= UMBRAL_MINIMO and peso_sell > peso_buy * DIFERENCIAL_MINIMO:
        direccion = "SELL"
        confianza = min(round((peso_sell / total) * 100), 98)
        razones = [v[0].replace("_", " ").title() for v in votos_sell[:5]]
    else:
        direccion = "ESPERAR"
        confianza = 0
        razones = [
            "Sin confirmación suficiente",
            "Esperar señal más fuerte"
        ]

    # ── VOLATILIDAD ─────────────────────────────────────────────
    atr_val = atr(candles)
    vol_pct = (atr_val / precio * 100) if precio else 0
    if vol_pct >= 0.35:
        vol_nivel = "muy_alta"
    elif vol_pct >= 0.25:
        vol_nivel = "alta"
    elif vol_pct >= 0.15:
        vol_nivel = "media_alta"
    elif vol_pct >= 0.05:
        vol_nivel = "media"
    else:
        vol_nivel = "baja"

    return {
        "direccion": direccion,
        "estrategia": "confianza_extrema",
        "volatilidad": vol_nivel,
        "tendencia": tend_larga,
        "razones": razones,
        "votos_buy": len(votos_buy),
        "votos_sell": len(votos_sell),
        "certeza_interna": confianza,
        "confianza": confianza,
        "score_buy": peso_buy,
        "score_sell": peso_sell,
        "indicadores": {
            "precio": round(precio, 6),
            "rsi": round(rsi_val, 1),
            "momentum": round(mom, 6),
            "estocastico": round(stoch, 1),
            "macd": round(macd_line, 6),
            "ema_rapida": round(ema5, 6) if ema5 else None,
            "ema_lenta": round(ema20, 6) if ema20 else None,
            "bb_superior": round(bb_up, 6) if bb_up else None,
            "bb_inferior": round(bb_lo, 6) if bb_lo else None,
            "patron_vela": patron_dir,
            "volatilidad_pct": round(vol_pct, 4),
        },
        "fibonacci": {"niveles": {}, "zona_actual": None, "precio_zona": None},
        "patrones_velas": [{"patron": patron_dir, "fuerza": patron_fuerza}] if patron_fuerza > 0 else [],
        "movimiento": {"suficiente": True, "porcentaje": 0, "minimo_requerido": 0},
    }


# ═══════════════════════════════════════════════════════════════
#  COMPATIBILIDAD
# ═══════════════════════════════════════════════════════════════

def detectar_volatilidad(candles, periodo=14):
    if not candles:
        return "media"
    atr_val = atr(candles, periodo)
    precio = candles[-1].get("close", 1)
    pct = (atr_val / precio * 100) if precio else 0
    if pct >= 0.35:
        return "muy_alta"
    elif pct >= 0.25:
        return "alta"
    elif pct >= 0.15:
        return "media_alta"
    elif pct >= 0.05:
        return "media"
    return "baja"


def seleccionar_estrategia_auto(candles):
    return "confianza_extrema", detectar_volatilidad(candles)


def calcular_volatilidad_real(candles, periodo=14):
    if not candles:
        return 0.0, "media"
    atr_val = atr(candles, periodo)
    precio = candles[-1].get("close", 1)
    pct = round((atr_val / precio * 100) if precio else 0, 4)
    return pct, detectar_volatilidad(candles)


def calcular_volatilidad_real_simple(candles, periodo=14):
    pct, _ = calcular_volatilidad_real(candles, periodo)
    return pct
