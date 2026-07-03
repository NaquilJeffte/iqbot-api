"""
analysis.py v4.3 — NUNCA ESPERAR, siempre BUY o SELL
- 10 indicadores en tiempo real
- Siempre elige la dirección más fuerte
- Confianza basada en consenso
- NUNCA devuelve ESPERAR
"""

import math
import time


# ═══════════════════════════════════════════════════════════════
#  INDICADORES
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
        return "UP", 0
    sub = closes[-ventana:]
    n = len(sub)
    x_mean = (n - 1) / 2
    y_mean = sum(sub) / n
    num = sum((i - x_mean) * (sub[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return "LATERAL", 0
    slope = num / den
    return ("UP" if slope > 0 else "DOWN"), abs(slope)


def patron_velas(candles):
    """Detecta patrones de velas japonesas"""
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

    # Engulfing alcista
    if (c1["close"] < c1["open"] and c["close"] > c["open"] and
            c["open"] <= c1["close"] and c["close"] >= c1["open"]):
        return "BUY", 90

    # Engulfing bajista
    if (c1["close"] > c1["open"] and c["close"] < c["open"] and
            c["open"] >= c1["close"] and c["close"] <= c1["open"]):
        return "SELL", 90

    # Tres soldados blancos
    if (c["close"] > c["open"] and c1["close"] > c1["open"] and
            c2["close"] > c2["open"] and
            c["close"] > c1["close"] > c2["close"]):
        return "BUY", 85

    # Tres cuervos negros
    if (c["close"] < c["open"] and c1["close"] < c1["open"] and
            c2["close"] < c2["open"] and
            c["close"] < c1["close"] < c2["close"]):
        return "SELL", 85

    # Martillo (hammer) alcista
    cuerpo = abs(c["close"] - c["open"])
    sombra_inf = min(c["close"], c["open"]) - c["low"]
    sombra_sup = c["high"] - max(c["close"], c["open"])
    if cuerpo > 0 and sombra_inf >= 2 * cuerpo and sombra_sup < cuerpo:
        return "BUY", 80

    # Estrella fugaz bajista
    if cuerpo > 0 and sombra_sup >= 2 * cuerpo and sombra_inf < cuerpo:
        return "SELL", 80

    # Doji
    if cuerpo < (c["high"] - c["low"]) * 0.1:
        return "NEUTRAL", 0

    # Vela actual
    if c["close"] > c["open"]:
        return "BUY", 55
    else:
        return "SELL", 55


# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL v4.3 — NUNCA ESPERAR
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    Motor v4.3 — NUNCA devuelve ESPERAR.
    Siempre elige BUY o SELL basado en votación ponderada.
    """
    if len(candles) < 10:
        ultima = candles[-1] if candles else {}
        return {
            "direccion": "BUY" if ultima.get("close", 0) >= ultima.get("open", 0) else "SELL",
            "confianza": 50,
            "estrategia": "automatica",
            "volatilidad": "media",
            "tendencia": "LATERAL",
            "razones": ["Datos limitados - usando vela actual"],
            "votos_buy": 1,
            "votos_sell": 0,
            "score_buy": 1,
            "score_sell": 0,
            "indicadores": {},
            "fibonacci": {},
            "patrones_velas": [],
            "timing": {},
        }

    closes = [c["close"] for c in candles]
    precio = closes[-1]

    # ── 10 INDICADORES ──────────────────────────────────────────
    votos_buy = []
    votos_sell = []

    # 1. TENDENCIA CORTA (5 velas)
    tend_corta, _ = tendencia_lineal(closes, min(5, len(closes)))
    if tend_corta == "UP":
        votos_buy.append(("tendencia_corta", 2))
    else:
        votos_sell.append(("tendencia_corta", 2))

    # 2. TENDENCIA LARGA (20 velas)
    tend_larga, fuerza = tendencia_lineal(closes, min(20, len(closes)))
    peso_tend = 3 if fuerza > 0.0001 else 1
    if tend_larga == "UP":
        votos_buy.append(("tendencia_larga", peso_tend))
    else:
        votos_sell.append(("tendencia_larga", peso_tend))

    # 3. EMA 5 vs EMA 20
    ema5 = ema(closes, min(5, len(closes)))
    ema20 = ema(closes, min(20, len(closes)))
    if ema5 and ema20:
        if ema5 > ema20:
            votos_buy.append(("ema_cruce", 2))
        else:
            votos_sell.append(("ema_cruce", 2))

    # 4. EMA 10 vs EMA 50
    ema10 = ema(closes, min(10, len(closes)))
    ema50 = ema(closes, min(50, len(closes))) if len(closes) >= 50 else None
    if ema10 and ema50:
        if ema10 > ema50:
            votos_buy.append(("ema_lenta", 3))
        else:
            votos_sell.append(("ema_lenta", 3))

    # 5. RSI
    rsi_val = rsi(closes, min(14, len(closes) // 2))
    if rsi_val < 30:
        votos_buy.append(("rsi_sobrevendido", 4))
    elif rsi_val < 45:
        votos_buy.append(("rsi_bajo", 2))
    elif rsi_val > 70:
        votos_sell.append(("rsi_sobrecomprado", 4))
    elif rsi_val > 55:
        votos_sell.append(("rsi_alto", 2))
    else:
        if tend_corta == "UP":
            votos_buy.append(("rsi_neutral", 1))
        else:
            votos_sell.append(("rsi_neutral", 1))

    # 6. MACD
    macd_line, signal_line = macd(closes)
    if macd_line > signal_line:
        votos_buy.append(("macd", 2))
    else:
        votos_sell.append(("macd", 2))

    # 7. MOMENTUM
    mom = momentum(closes, min(5, len(closes) - 1))
    mom_largo = momentum(closes, min(10, len(closes) - 1))
    if mom > 0 and mom_largo > 0:
        votos_buy.append(("momentum", 3))
    elif mom < 0 and mom_largo < 0:
        votos_sell.append(("momentum", 3))
    elif mom > 0:
        votos_buy.append(("momentum_corto", 1))
    else:
        votos_sell.append(("momentum_corto", 1))

    # 8. BOLLINGER BANDS
    bb_up, bb_mid, bb_lo = bollinger(closes, min(20, len(closes)))
    if bb_up and bb_lo:
        if precio <= bb_lo:
            votos_buy.append(("bollinger_sobrevendido", 4))
        elif precio >= bb_up:
            votos_sell.append(("bollinger_sobrecomprado", 4))
        elif precio < bb_mid:
            votos_buy.append(("bollinger_bajo", 1))
        else:
            votos_sell.append(("bollinger_alto", 1))

    # 9. ESTOCÁSTICO
    stoch = stochastico(closes, min(14, len(closes)))
    if stoch < 20:
        votos_buy.append(("estocastico_bajo", 3))
    elif stoch < 40:
        votos_buy.append(("estocastico_neutro_bajo", 1))
    elif stoch > 80:
        votos_sell.append(("estocastico_alto", 3))
    elif stoch > 60:
        votos_sell.append(("estocastico_neutro_alto", 1))

    # 10. PATRÓN DE VELAS
    patron_dir, patron_fuerza = patron_velas(candles)
    if patron_dir == "BUY":
        peso_patron = 5 if patron_fuerza >= 85 else 3 if patron_fuerza >= 75 else 2
        votos_buy.append(("patron_vela", peso_patron))
    elif patron_dir == "SELL":
        peso_patron = 5 if patron_fuerza >= 85 else 3 if patron_fuerza >= 75 else 2
        votos_sell.append(("patron_vela", peso_patron))

    # ── DECISIÓN - NUNCA ESPERAR ──────────────────────────────
    peso_buy = sum(v[1] for v in votos_buy)
    peso_sell = sum(v[1] for v in votos_sell)
    total = peso_buy + peso_sell or 1

    # SIEMPRE elegir la dirección con más peso
    if peso_buy >= peso_sell:
        direccion = "BUY"
        confianza = round((peso_buy / total) * 100)
        razones = [v[0].replace("_", " ").title() for v in votos_buy[:5]]
        votos_ganadores = votos_buy
    else:
        direccion = "SELL"
        confianza = round((peso_sell / total) * 100)
        razones = [v[0].replace("_", " ").title() for v in votos_sell[:5]]
        votos_ganadores = votos_sell

    # Confianza mínima 50%
    confianza = max(50, min(confianza, 95))

    # ── TIMING ─────────────────────────────────────────────────
    ahora = time.time()
    seg_restantes = timeframe_seg - (ahora % timeframe_seg)
    timing = {
        "segundos_restantes": round(seg_restantes, 1),
        "puede_entrar": True,
        "mensaje": f"Entrar ahora — {round(seg_restantes)}s",
    }

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
        "estrategia": "automatica",
        "volatilidad": vol_nivel,
        "tendencia": tend_larga,
        "timing": timing,
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
    return "automatica", detectar_volatilidad(candles)


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


def escanear_mejores_activos(candles_por_activo, timeframe_seg=60):
    resultados = []
    for activo, candles in candles_por_activo.items():
        if not candles or len(candles) < 5:
            continue
        try:
            r = generar_senal(candles, "auto", timeframe_seg)
            resultados.append({
                "activo": activo,
                "direccion": r["direccion"],
                "certeza": r.get("confianza", 50),
                "volatilidad": r.get("volatilidad", "media"),
                "razones": r.get("razones", []),
                "analisis": r,
            })
        except Exception:
            continue
    resultados.sort(key=lambda x: x["certeza"], reverse=True)
    if not resultados:
        return {"ok": False, "mensaje": "Sin datos", "activos": []}
    mejor = resultados[0]
    return {
        "ok": True,
        "mensaje": f"{mejor['activo']} → {mejor['direccion']} (confianza: {mejor['certeza']}%)",
        "mejor": mejor,
        "activos": resultados[:5],
    }
