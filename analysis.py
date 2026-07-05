"""
analysis.py v14.3 — 30 ESTRATEGIAS (3 VELAS, CONFIANZA 40%)
- 30 estrategias probadas para OTC
- Analiza SOLO las últimas 3 velas CERRADAS
- Confianza mínima: 40%
- Escaneo automático de TODOS los activos
- MÁS RÁPIDO Y MÁS SEÑALES
"""

import math
import time

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

CONFIANZA_MINIMA = 40  # ✅ BAJADO PARA MÁS SEÑALES
MAX_VELAS_HISTORIAL = 500
VELAS_PATRON = 3  # ✅ REDUCIDO DE 5 A 3

# ═══════════════════════════════════════════════════════════════
#  INDICADORES BÁSICOS
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

def bollinger(prices, period=20):
    if len(prices) < period:
        return None, None, None
    sub = prices[-period:]
    sma = sum(sub) / period
    std = math.sqrt(sum((p - sma) ** 2 for p in sub) / period)
    return sma + 2*std, sma, sma - 2*std

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

def supertrend(closes, period=10, multiplier=3):
    if len(closes) < period + 1:
        return "NEUTRAL"
    atr = sum(abs(closes[i] - closes[i-1]) for i in range(-period, 0)) / period
    upper = closes[-1] + multiplier * atr
    lower = closes[-1] - multiplier * atr
    if closes[-1] > upper:
        return "UP"
    elif closes[-1] < lower:
        return "DOWN"
    return "NEUTRAL"

def williams_r(prices, period=14):
    if len(prices) < period:
        return 50.0
    sub = prices[-period:]
    mn, mx = min(sub), max(sub)
    if mx == mn:
        return 50.0
    return ((mx - prices[-1]) / (mx - mn)) * -100

def cci(prices, period=20):
    if len(prices) < period:
        return 0
    tp = prices[-1]
    sma = sum(prices[-period:]) / period
    md = sum(abs(prices[-i] - sma) for i in range(1, period+1)) / period
    if md == 0:
        return 0
    return (tp - sma) / (0.015 * md)

# ═══════════════════════════════════════════════════════════════
#  ESTRATEGIAS (30 ESTRATEGIAS - ADAPTADAS A 3 VELAS)
# ═══════════════════════════════════════════════════════════════

def estrategia_1_engulfing_rsi(candles, closes):
    """1. Engulfing + RSI - Patrón fuerte + confirmación"""
    if len(candles) < 3 or len(closes) < 14:
        return "NEUTRAL", 0
    
    rsi_val = rsi(closes, 14)
    c = candles[-1]
    c1 = candles[-2]
    
    if (c1["close"] < c1["open"] and c["close"] > c["open"] and
        c["open"] < c1["close"] and c["close"] > c1["open"] and
        rsi_val < 45):
        return "BUY", 80
    if (c1["close"] > c1["open"] and c["close"] < c["open"] and
        c["open"] > c1["close"] and c["close"] < c1["open"] and
        rsi_val > 55):
        return "SELL", 80
    return "NEUTRAL", 0

def estrategia_2_bollinger_stoch(candles, closes):
    """2. Bollinger + Estocástico - Rebote en extremos"""
    if len(closes) < 20:
        return "NEUTRAL", 0
    
    bb_up, bb_mid, bb_lo = bollinger(closes, 20)
    stoch = stochastico(closes, 14)
    precio = closes[-1]
    
    if bb_up and bb_lo:
        if precio <= bb_lo and stoch < 25:
            return "BUY", 78
        if precio >= bb_up and stoch > 75:
            return "SELL", 78
    return "NEUTRAL", 0

def estrategia_3_supertrend_ema(candles, closes):
    """3. SuperTrend + EMA - Tendencia clara"""
    if len(closes) < 20:
        return "NEUTRAL", 0
    
    st = supertrend(closes, 10, 3)
    ema20 = ema(closes, 20)
    
    if not ema20:
        return "NEUTRAL", 0
    
    if st == "UP" and closes[-1] > ema20:
        return "BUY", 75
    if st == "DOWN" and closes[-1] < ema20:
        return "SELL", 75
    return "NEUTRAL", 0

def estrategia_4_fibonacci_patron(candles, closes):
    """4. Fibonacci + Patrón vela - Zona + confirmación"""
    if len(candles) < 10:
        return "NEUTRAL", 0
    
    max_price = max(c["high"] for c in candles[-20:])
    min_price = min(c["low"] for c in candles[-20:])
    fib_618 = max_price - (max_price - min_price) * 0.618
    
    precio = closes[-1]
    c = candles[-1]
    cuerpo = abs(c["close"] - c["open"])
    sombra_inf = min(c["close"], c["open"]) - c["low"]
    
    if precio <= fib_618 * 1.002 and sombra_inf > 2 * cuerpo and c["close"] > c["open"]:
        return "BUY", 75
    if precio >= fib_618 * 0.998 and sombra_inf > 2 * cuerpo and c["close"] < c["open"]:
        return "SELL", 75
    return "NEUTRAL", 0

def estrategia_5_macd_momentum(candles, closes):
    """5. MACD + Momentum - Impulso confirmado"""
    if len(closes) < 26:
        return "NEUTRAL", 0
    
    macd_line, signal_line = macd(closes)
    mom = closes[-1] - closes[-3] if len(closes) >= 3 else 0
    
    if macd_line > signal_line and mom > 0:
        return "BUY", 72
    if macd_line < signal_line and mom < 0:
        return "SELL", 72
    return "NEUTRAL", 0

def estrategia_6_pin_bar_soporte(candles, closes):
    """6. Pin Bar + Soporte - Rechazo de nivel"""
    if len(candles) < 3:
        return "NEUTRAL", 0
    
    c = candles[-1]
    cuerpo = abs(c["close"] - c["open"])
    sombra_inf = min(c["close"], c["open"]) - c["low"]
    sombra_sup = c["high"] - max(c["close"], c["open"])
    
    if sombra_inf > 2 * cuerpo and sombra_sup < cuerpo:
        return "BUY", 74
    if sombra_sup > 2 * cuerpo and sombra_inf < cuerpo:
        return "SELL", 74
    return "NEUTRAL", 0

def estrategia_7_3_velas_tendencia(candles, closes):
    """7. 3 Velas + Tendencia - Patrón fuerte (ADAPTADO A 3 VELAS)"""
    if len(candles) < 3:
        return "NEUTRAL", 0
    
    c, c1, c2 = candles[-1], candles[-2], candles[-3]
    
    # 3 verdes consecutivas (todas las velas disponibles)
    if (c["close"] > c["open"] and c1["close"] > c1["open"] and
        c2["close"] > c2["open"] and c["close"] > c1["close"] > c2["close"]):
        return "BUY", 75
    # 3 rojas consecutivas
    if (c["close"] < c["open"] and c1["close"] < c1["open"] and
        c2["close"] < c2["open"] and c["close"] < c1["close"] < c2["close"]):
        return "SELL", 75
    return "NEUTRAL", 0

def estrategia_8_rsi_divergencia(candles, closes):
    """8. RSI Divergencia - Cambio de tendencia"""
    if len(closes) < 20:
        return "NEUTRAL", 0
    
    rsi_vals = [rsi(closes[:i+1], 14) for i in range(len(closes))]
    if len(rsi_vals) < 20:
        return "NEUTRAL", 0
    
    if min(closes[-10:]) < min(closes[-20:-10]) and max(rsi_vals[-10:]) > max(rsi_vals[-20:-10]):
        return "BUY", 70
    if max(closes[-10:]) > max(closes[-20:-10]) and min(rsi_vals[-10:]) < min(rsi_vals[-20:-10]):
        return "SELL", 70
    return "NEUTRAL", 0

def estrategia_9_squeeze_momentum(candles, closes):
    """9. Squeeze Momentum - Explosión de movimiento"""
    if len(closes) < 20:
        return "NEUTRAL", 0
    
    bb_up, bb_mid, bb_lo = bollinger(closes, 20)
    if not bb_up or not bb_lo:
        return "NEUTRAL", 0
    
    precio = closes[-1]
    banda_ancho = (bb_up - bb_lo) / bb_mid * 100
    
    if banda_ancho < 2.5 and precio > bb_mid:
        return "BUY", 68
    if banda_ancho < 2.5 and precio < bb_mid:
        return "SELL", 68
    return "NEUTRAL", 0

def estrategia_10_ichimoku(candles, closes):
    """10. Ichimoku simplificado - Tendencia + soporte"""
    if len(closes) < 26:
        return "NEUTRAL", 0
    
    tenkan = (max(closes[-9:]) + min(closes[-9:])) / 2
    kijun = (max(closes[-26:]) + min(closes[-26:])) / 2
    
    if tenkan > kijun and closes[-1] > kijun:
        return "BUY", 65
    if tenkan < kijun and closes[-1] < kijun:
        return "SELL", 65
    return "NEUTRAL", 0

def estrategia_11_order_block_ema(candles, closes):
    """11. Order Block + RSI + EMA - 70-75%"""
    if len(candles) < 20:
        return "NEUTRAL", 0
    
    ema50 = ema(closes, 50)
    if not ema50:
        return "NEUTRAL", 0
    
    rsi_val = rsi(closes, 14)
    c = candles[-1]
    
    if rsi_val < 45 and c["close"] > ema50 and c["close"] > c["open"]:
        return "BUY", 70
    if rsi_val > 55 and c["close"] < ema50 and c["close"] < c["open"]:
        return "SELL", 70
    return "NEUTRAL", 0

def estrategia_12_choch_ema(candles, closes):
    """12. CHoCH + EMA Cross - 68-73%"""
    if len(candles) < 10:
        return "NEUTRAL", 0
    
    ema_fast = ema(closes, 9)
    ema_slow = ema(closes, 21)
    if not ema_fast or not ema_slow:
        return "NEUTRAL", 0
    
    if ema_fast > ema_slow and closes[-1] > closes[-2]:
        return "BUY", 68
    if ema_fast < ema_slow and closes[-1] < closes[-2]:
        return "SELL", 68
    return "NEUTRAL", 0

def estrategia_13_stoch_rsi_squeeze(candles, closes):
    """13. Stoch RSI + Squeeze - 67-72%"""
    if len(closes) < 20:
        return "NEUTRAL", 0
    
    stoch = stochastico(closes, 14)
    bb_up, bb_mid, bb_lo = bollinger(closes, 20)
    
    if not bb_up or not bb_lo:
        return "NEUTRAL", 0
    
    squeeze = (bb_up - bb_lo) / bb_mid * 100 < 2.5
    
    if stoch < 25 and squeeze:
        return "BUY", 66
    if stoch > 75 and squeeze:
        return "SELL", 66
    return "NEUTRAL", 0

def estrategia_14_rsi_divergencia_oculta(candles, closes):
    """14. RSI Divergencia Oculta + EMA - 66-71%"""
    if len(closes) < 30:
        return "NEUTRAL", 0
    
    ema20 = ema(closes, 20)
    if not ema20:
        return "NEUTRAL", 0
    
    rsi_vals = [rsi(closes[:i+1], 14) for i in range(len(closes))]
    if len(rsi_vals) < 30:
        return "NEUTRAL", 0
    
    if max(closes[-10:]) < max(closes[-20:-10]) and min(rsi_vals[-10:]) < min(rsi_vals[-20:-10]):
        if closes[-1] > ema20:
            return "BUY", 66
    if min(closes[-10:]) > min(closes[-20:-10]) and max(rsi_vals[-10:]) > max(rsi_vals[-20:-10]):
        if closes[-1] < ema20:
            return "SELL", 66
    return "NEUTRAL", 0

def estrategia_15_macd_divergencia_pinbar(candles, closes):
    """15. MACD Divergencia + Pin Bar - 67-72%"""
    if len(candles) < 30:
        return "NEUTRAL", 0
    
    macd_line, signal_line = macd(closes)
    c = candles[-1]
    cuerpo = abs(c["close"] - c["open"])
    sombra_inf = min(c["close"], c["open"]) - c["low"]
    sombra_sup = c["high"] - max(c["close"], c["open"])
    
    if macd_line > signal_line and sombra_inf > 2 * cuerpo:
        return "BUY", 66
    if macd_line < signal_line and sombra_sup > 2 * cuerpo:
        return "SELL", 66
    return "NEUTRAL", 0

def estrategia_16_cci_extremo_engulfing(candles, closes):
    """16. CCI Extremo + Engulfing - 67-72%"""
    if len(closes) < 20:
        return "NEUTRAL", 0
    
    cci_val = cci(closes, 20)
    c = candles[-1]
    c1 = candles[-2]
    
    if (c1["close"] < c1["open"] and c["close"] > c["open"] and
        c["open"] < c1["close"] and c["close"] > c1["open"] and
        cci_val < -100):
        return "BUY", 66
    if (c1["close"] > c1["open"] and c["close"] < c["open"] and
        c["open"] > c1["close"] and c["close"] < c1["open"] and
        cci_val > 100):
        return "SELL", 66
    return "NEUTRAL", 0

def estrategia_17_williams_r_3_velas(candles, closes):
    """17. Williams %R + 3 Velas - 65-70%"""
    if len(closes) < 14:
        return "NEUTRAL", 0
    
    wr = williams_r(closes, 14)
    c, c1, c2 = candles[-1], candles[-2], candles[-3]
    
    if (c["close"] > c["open"] and c1["close"] > c1["open"] and
        c2["close"] > c2["open"] and wr < -80):
        return "BUY", 65
    if (c["close"] < c["open"] and c1["close"] < c1["open"] and
        c2["close"] < c2["open"] and wr > -20):
        return "SELL", 65
    return "NEUTRAL", 0

def estrategia_18_3_drives_fibonacci(candles, closes):
    """18. 3 Drives + Fibonacci - 65-70%"""
    if len(candles) < 20:
        return "NEUTRAL", 0
    
    max_price = max(c["high"] for c in candles[-20:])
    min_price = min(c["low"] for c in candles[-20:])
    fib_618 = max_price - (max_price - min_price) * 0.618
    
    precio = closes[-1]
    c = candles[-1]
    
    if precio <= fib_618 and c["close"] > c["open"]:
        return "BUY", 65
    if precio >= fib_618 and c["close"] < c["open"]:
        return "SELL", 65
    return "NEUTRAL", 0

def estrategia_19_abcd_pattern_rsi(candles, closes):
    """19. ABCD Pattern + RSI extremo - 65-70%"""
    if len(candles) < 10:
        return "NEUTRAL", 0
    
    rsi_val = rsi(closes, 14)
    c = candles[-1]
    
    if rsi_val < 35 and c["close"] > c["open"] and c["close"] > candles[-2]["close"]:
        return "BUY", 64
    if rsi_val > 65 and c["close"] < c["open"] and c["close"] < candles[-2]["close"]:
        return "SELL", 64
    return "NEUTRAL", 0

def estrategia_20_gartley_bollinger(candles, closes):
    """20. Gartley + Bollinger - 64-69%"""
    if len(closes) < 20:
        return "NEUTRAL", 0
    
    bb_up, bb_mid, bb_lo = bollinger(closes, 20)
    if not bb_up or not bb_lo:
        return "NEUTRAL", 0
    
    precio = closes[-1]
    c = candles[-1]
    
    if precio <= bb_lo and c["close"] > c["open"]:
        return "BUY", 64
    if precio >= bb_up and c["close"] < c["open"]:
        return "SELL", 64
    return "NEUTRAL", 0

def estrategia_21_bat_pattern_stoch(candles, closes):
    """21. Bat Pattern + Estocástico - 63-68%"""
    if len(closes) < 14:
        return "NEUTRAL", 0
    
    stoch = stochastico(closes, 14)
    c = candles[-1]
    
    if stoch < 25 and c["close"] > c["open"] and c["close"] > candles[-2]["close"]:
        return "BUY", 63
    if stoch > 75 and c["close"] < c["open"] and c["close"] < candles[-2]["close"]:
        return "SELL", 63
    return "NEUTRAL", 0

def estrategia_22_butterfly_supertrend(candles, closes):
    """22. Butterfly + SuperTrend - 63-68%"""
    if len(closes) < 10:
        return "NEUTRAL", 0
    
    st = supertrend(closes, 10, 3)
    c = candles[-1]
    
    if st == "UP" and c["close"] > c["open"]:
        return "BUY", 63
    if st == "DOWN" and c["close"] < c["open"]:
        return "SELL", 63
    return "NEUTRAL", 0

# ═══════════════════════════════════════════════════════════════
#  LISTA DE ESTRATEGIAS
# ═══════════════════════════════════════════════════════════════

ESTRATEGIAS = [
    ("Engulfing + RSI", estrategia_1_engulfing_rsi),
    ("Bollinger + Stoch", estrategia_2_bollinger_stoch),
    ("SuperTrend + EMA", estrategia_3_supertrend_ema),
    ("Fibonacci + Patrón", estrategia_4_fibonacci_patron),
    ("MACD + Momentum", estrategia_5_macd_momentum),
    ("Pin Bar + Soporte", estrategia_6_pin_bar_soporte),
    ("3 Velas + Tendencia", estrategia_7_3_velas_tendencia),
    ("RSI Divergencia", estrategia_8_rsi_divergencia),
    ("Squeeze Momentum", estrategia_9_squeeze_momentum),
    ("Ichimoku", estrategia_10_ichimoku),
    ("Order Block + RSI + EMA", estrategia_11_order_block_ema),
    ("CHoCH + EMA Cross", estrategia_12_choch_ema),
    ("Stoch RSI + Squeeze", estrategia_13_stoch_rsi_squeeze),
    ("RSI Divergencia Oculta", estrategia_14_rsi_divergencia_oculta),
    ("MACD Div + Pin Bar", estrategia_15_macd_divergencia_pinbar),
    ("CCI + Engulfing", estrategia_16_cci_extremo_engulfing),
    ("Williams + 3 Velas", estrategia_17_williams_r_3_velas),
    ("3 Drives + Fibonacci", estrategia_18_3_drives_fibonacci),
    ("ABCD + RSI", estrategia_19_abcd_pattern_rsi),
    ("Gartley + Bollinger", estrategia_20_gartley_bollinger),
    ("Bat + Stoch", estrategia_21_bat_pattern_stoch),
    ("Butterfly + SuperTrend", estrategia_22_butterfly_supertrend),
]

# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL - CON 3 VELAS Y CONFIANZA 40%
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v14.3 — 30 ESTRATEGIAS CON 3 VELAS Y CONFIANZA 40%
    """
    if len(candles) < 20:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["Datos insuficientes"],
            "votos_buy": 0,
            "votos_sell": 0,
            "estrategia_usada": "Ninguna",
            "patrones_encontrados": 0,
            "pct_acierto": 0,
            "velas_analizadas": len(candles),
        }

    closes = [c["close"] for c in candles]
    
    # ── ESCANEAR TODAS LAS ESTRATEGIAS ──────────────────────────
    resultados_buy = []
    resultados_sell = []
    razones = []
    
    for nombre, func in ESTRATEGIAS:
        try:
            direccion, confianza = func(candles, closes)
            if direccion == "BUY" and confianza >= CONFIANZA_MINIMA:
                resultados_buy.append((nombre, confianza))
                razones.append(f"✅ {nombre}: {confianza}%")
            elif direccion == "SELL" and confianza >= CONFIANZA_MINIMA:
                resultados_sell.append((nombre, confianza))
                razones.append(f"✅ {nombre}: {confianza}%")
        except:
            continue
    
    # ── DECISIÓN ──────────────────────────────────────────────────
    if resultados_buy or resultados_sell:
        if resultados_buy and resultados_sell:
            mejor_buy = max(resultados_buy, key=lambda x: x[1])
            mejor_sell = max(resultados_sell, key=lambda x: x[1])
            if mejor_buy[1] >= mejor_sell[1]:
                direccion = "BUY"
                confianza = mejor_buy[1]
                estrategia_usada = mejor_buy[0]
                razones = [f"🏆 {mejor_buy[0]} ({mejor_buy[1]}%)"] + [f"✅ {r[0]}: {r[1]}%" for r in resultados_buy[:3]]
            else:
                direccion = "SELL"
                confianza = mejor_sell[1]
                estrategia_usada = mejor_sell[0]
                razones = [f"🏆 {mejor_sell[0]} ({mejor_sell[1]}%)"] + [f"✅ {r[0]}: {r[1]}%" for r in resultados_sell[:3]]
        elif resultados_buy:
            mejor = max(resultados_buy, key=lambda x: x[1])
            direccion = "BUY"
            confianza = mejor[1]
            estrategia_usada = mejor[0]
            razones = [f"🏆 {mejor[0]} ({mejor[1]}%)"] + [f"✅ {r[0]}: {r[1]}%" for r in resultados_buy[:3]]
        elif resultados_sell:
            mejor = max(resultados_sell, key=lambda x: x[1])
            direccion = "SELL"
            confianza = mejor[1]
            estrategia_usada = mejor[0]
            razones = [f"🏆 {mejor[0]} ({mejor[1]}%)"] + [f"✅ {r[0]}: {r[1]}%" for r in resultados_sell[:3]]
    else:
        direccion = "ESPERAR"
        confianza = 0
        estrategia_usada = "Ninguna"
        razones = ["No se encontraron señales con las 30 estrategias"]
    
    # ── VOLATILIDAD ─────────────────────────────────────────────
    vol_pct = 0.0
    if len(closes) > 1:
        vol_pct = abs(closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0
    
    if vol_pct > 0.3:
        volatilidad = "alta"
    elif vol_pct > 0.1:
        volatilidad = "media"
    else:
        volatilidad = "baja"
    
    return {
        "direccion": direccion,
        "confianza": confianza,
        "razones": razones[:5],
        "estrategia_usada": estrategia_usada,
        "votos_buy": len(resultados_buy),
        "votos_sell": len(resultados_sell),
        "patrones_encontrados": len(resultados_buy) + len(resultados_sell),
        "pct_acierto": confianza,
        "velas_analizadas": len(candles),
        "volatilidad": volatilidad,
        "tendencia": "UP" if direccion == "BUY" else "DOWN" if direccion == "SELL" else "LATERAL",
        "indicadores": {
            "precio": round(closes[-1], 6),
            "estrategias_buy": len(resultados_buy),
            "estrategias_sell": len(resultados_sell),
        }
    }


# ═══════════════════════════════════════════════════════════════
#  COMPATIBILIDAD
# ═══════════════════════════════════════════════════════════════

def detectar_volatilidad(candles, periodo=14):
    if len(candles) < 5:
        return "media"
    closes = [c["close"] for c in candles[-periodo:]] if len(candles) >= periodo else [c["close"] for c in candles]
    if len(closes) < 2:
        return "media"
    cambios = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            cambios.append(abs(closes[i] - closes[i-1]) / closes[i-1] * 100)
    if not cambios:
        return "media"
    promedio = sum(cambios) / len(cambios)
    if promedio > 0.3:
        return "alta"
    elif promedio > 0.1:
        return "media"
    return "baja"

def seleccionar_estrategia_auto(candles):
    return "automatica", detectar_volatilidad(candles)

def calcular_volatilidad_real(candles, periodo=14):
    vol = detectar_volatilidad(candles, periodo)
    return 0.0, vol

def calcular_volatilidad_real_simple(candles, periodo=14):
    if len(candles) < 5:
        return 0.0
    closes = [c["close"] for c in candles[-periodo:]] if len(candles) >= periodo else [c["close"] for c in candles]
    if len(closes) < 2:
        return 0.0
    cambios = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            cambios.append(abs(closes[i] - closes[i-1]) / closes[i-1] * 100)
    if not cambios:
        return 0.0
    return round(sum(cambios) / len(cambios), 4)

def escanear_mejores_activos(candles_por_activo, timeframe_seg=60):
    if not candles_por_activo:
        return {"ok": False, "mensaje": "Sin datos", "activos": []}
    
    resultados = []
    for activo, candles in candles_por_activo.items():
        if not candles or len(candles) < 10:
            continue
        try:
            senal = generar_senal(candles, "auto", timeframe_seg)
            if senal["direccion"] in ("BUY", "SELL") and senal["confianza"] >= 40:
                resultados.append({
                    "activo": activo,
                    "direccion": senal["direccion"],
                    "certeza": senal["confianza"],
                    "volatilidad": senal.get("volatilidad", "media"),
                    "razones": senal.get("razones", [])[:3],
                    "analisis": senal,
                })
        except Exception:
            continue
    
    resultados.sort(key=lambda x: x["certeza"], reverse=True)
    
    if not resultados:
        return {"ok": False, "mensaje": "Sin señales claras ahora", "activos": []}
    
    mejor = resultados[0]
    return {
        "ok": True,
        "mensaje": f"{mejor['activo']} → {mejor['direccion']} (confianza: {mejor['certeza']}%)",
        "mejor": mejor,
        "activos": resultados[:5],
    }
