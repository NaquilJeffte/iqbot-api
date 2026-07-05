"""
analysis.py v16.0 — ESTRATEGIA COMBINADA: PRICE ACTION + TENDENCIA INTELIGENTE
- Price Action + Soportes y Resistencias (50% peso)
- Tendencia Inteligente: EMA + ADX + RSI (50% peso)
- Solo opera cuando ambas estrategias están alineadas
- Puntuación combinada >= 80
- ¡MÁXIMA PRECISIÓN!
"""

import math
import time

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

PUNTAJE_MINIMO = 80
MAX_VELAS_HISTORIAL = 300
PERIODO_EMA_RAPIDA = 20
PERIODO_EMA_MEDIA = 50
PERIODO_EMA_LENTA = 200
PERIODO_RSI = 14
PERIODO_ADX = 14

# ═══════════════════════════════════════════════════════════════
#  ESTRATEGIA 1: PRICE ACTION + SOPORTES Y RESISTENCIAS
# ═══════════════════════════════════════════════════════════════

def encontrar_soportes_resistencias(candles, ventana=30):
    """
    Encuentra soportes y resistencias automáticamente
    """
    if len(candles) < ventana:
        return [], []
    
    soportes = []
    resistencias = []
    
    # Buscar máximos y mínimos locales
    for i in range(ventana, len(candles) - 1):
        # Máximo local (resistencia)
        if (candles[i]["high"] > candles[i-1]["high"] and 
            candles[i]["high"] > candles[i+1]["high"]):
            resistencias.append(candles[i]["high"])
        
        # Mínimo local (soporte)
        if (candles[i]["low"] < candles[i-1]["low"] and 
            candles[i]["low"] < candles[i+1]["low"]):
            soportes.append(candles[i]["low"])
    
    # Filtrar niveles cercanos (agrupar)
    soportes_filtrados = []
    for s in soportes:
        if not any(abs(s - x) / s < 0.001 for x in soportes_filtrados):
            soportes_filtrados.append(s)
    
    resistencias_filtradas = []
    for r in resistencias:
        if not any(abs(r - x) / r < 0.001 for x in resistencias_filtradas):
            resistencias_filtradas.append(r)
    
    return soportes_filtrados, resistencias_filtradas

def detectar_patron_vela(candles, idx):
    """
    Detecta patrones de velas individuales
    """
    if idx < 0 or idx >= len(candles):
        return "NEUTRAL", 0
    
    vela = candles[idx]
    open_p = vela["open"]
    close_p = vela["close"]
    high_p = vela["high"]
    low_p = vela["low"]
    
    cuerpo = abs(close_p - open_p)
    rango = high_p - low_p
    if rango == 0:
        return "NEUTRAL", 0
    
    rel_cuerpo = cuerpo / rango
    mecha_sup = high_p - max(close_p, open_p)
    mecha_inf = min(close_p, open_p) - low_p
    rel_mecha_sup = mecha_sup / rango
    rel_mecha_inf = mecha_inf / rango
    
    # MARUBOZU
    if rel_mecha_sup < 0.05 and rel_mecha_inf < 0.05 and rel_cuerpo > 0.6:
        if close_p > open_p:
            return "MARUBOZU_ALCISTA", 95
        else:
            return "MARUBOZU_BAJISTA", 95
    
    # MARTILLO
    if rel_mecha_inf > 0.6 and rel_cuerpo < 0.3 and rel_mecha_sup < 0.15:
        if close_p > open_p:
            return "MARTILLO_ALCISTA", 85
        else:
            return "MARTILLO_BAJISTA", 85
    
    # ESTRELLA FUGAZ
    if rel_mecha_sup > 0.6 and rel_cuerpo < 0.3 and rel_mecha_inf < 0.15:
        if close_p > open_p:
            return "ESTRELLA_FUGAZ_ALCISTA", 85
        else:
            return "ESTRELLA_FUGAZ_BAJISTA", 85
    
    # DOJI
    if rel_cuerpo < 0.1:
        return "DOJI", 50
    
    # ENVOLVENTE (necesita vela anterior)
    if idx > 0:
        vela_ant = candles[idx-1]
        if (vela_ant["close"] < vela_ant["open"] and 
            close_p > open_p and
            open_p <= vela_ant["close"] and 
            close_p >= vela_ant["open"]):
            return "ENVOLVENTE_ALCISTA", 90
        if (vela_ant["close"] > vela_ant["open"] and 
            close_p < open_p and
            open_p >= vela_ant["close"] and 
            close_p <= vela_ant["open"]):
            return "ENVOLVENTE_BAJISTA", 90
    
    # PIN BAR (mecha larga en un lado)
    if rel_mecha_sup > 0.5 and rel_mecha_inf < 0.15:
        if close_p > open_p:
            return "PIN_BAR_ALCISTA", 80
        else:
            return "PIN_BAR_BAJISTA", 80
    
    if rel_mecha_inf > 0.5 and rel_mecha_sup < 0.15:
        if close_p > open_p:
            return "PIN_BAR_ALCISTA", 80
        else:
            return "PIN_BAR_BAJISTA", 80
    
    return "NEUTRAL", 0

def analizar_contexto_velas(candles):
    """
    Analiza el contexto de las últimas 5 velas
    """
    if len(candles) < 5:
        return 0, "NEUTRAL"
    
    ultimas_5 = candles[-5:]
    
    # Contar velas alcistas/bajistas
    verdes = sum(1 for v in ultimas_5 if v["close"] > v["open"])
    rojas = 5 - verdes
    
    # Fuerza del movimiento
    cambios = []
    for i in range(1, len(ultimas_5)):
        cambio = (ultimas_5[i]["close"] - ultimas_5[i-1]["close"]) / ultimas_5[i-1]["close"] * 100
        cambios.append(cambio)
    
    if not cambios:
        return 0, "NEUTRAL"
    
    promedio_cambio = sum(cambios) / len(cambios)
    
    if verdes >= 4 and promedio_cambio > 0:
        return 80, "FUERTE_ALCISTA"
    elif rojas >= 4 and promedio_cambio < 0:
        return 80, "FUERTE_BAJISTA"
    elif verdes >= 3 and promedio_cambio > 0:
        return 60, "ALCISTA"
    elif rojas >= 3 and promedio_cambio < 0:
        return 60, "BAJISTA"
    else:
        return 30, "LATERAL"

def estrategia_price_action(candles):
    """
    ESTRATEGIA 1: Price Action + Soportes y Resistencias
    """
    if len(candles) < 30:
        return "NEUTRAL", 0, ["Datos insuficientes para Price Action"]
    
    razones = []
    puntaje = 0
    direccion = "NEUTRAL"
    
    # 1. Encontrar soportes y resistencias
    soportes, resistencias = encontrar_soportes_resistencias(candles, 30)
    
    # 2. Analizar la última vela
    ultima_vela = candles[-1]
    patron, fuerza_patron = detectar_patron_vela(candles, -1)
    
    # 3. Analizar contexto de últimas 5 velas
    contexto_puntaje, contexto_direccion = analizar_contexto_velas(candles)
    
    # 4. Detectar rechazos o rompimientos
    precio_actual = ultima_vela["close"]
    rechazo = False
    rompimiento = False
    
    # Rechazo en soporte
    for s in soportes:
        if abs(precio_actual - s) / s < 0.001 and ultima_vela["close"] > ultima_vela["open"]:
            rechazo = True
            razones.append(f"✅ Rechazo en soporte {s:.5f}")
            puntaje += 25
    
    # Rechazo en resistencia
    for r in resistencias:
        if abs(precio_actual - r) / r < 0.001 and ultima_vela["close"] < ultima_vela["open"]:
            rechazo = True
            razones.append(f"✅ Rechazo en resistencia {r:.5f}")
            puntaje += 25
    
    # Rompimiento
    if not rechazo:
        for r in resistencias:
            if precio_actual > r and ultima_vela["close"] > ultima_vela["open"]:
                rompimiento = True
                razones.append(f"✅ Rompimiento de resistencia {r:.5f}")
                puntaje += 20
        for s in soportes:
            if precio_actual < s and ultima_vela["close"] < ultima_vela["open"]:
                rompimiento = True
                razones.append(f"✅ Rompimiento de soporte {s:.5f}")
                puntaje += 20
    
    # 5. Patrón de vela (peso 30)
    if fuerza_patron >= 80:
        if patron in ["MARUBOZU_ALCISTA", "ENVOLVENTE_ALCISTA", "MARTILLO_ALCISTA", "PIN_BAR_ALCISTA"]:
            puntaje += 30
            razones.append(f"✅ Patrón ALCISTA: {patron} ({fuerza_patron}%)")
            if direccion == "NEUTRAL":
                direccion = "BUY"
        elif patron in ["MARUBOZU_BAJISTA", "ENVOLVENTE_BAJISTA", "ESTRELLA_FUGAZ_BAJISTA", "PIN_BAR_BAJISTA"]:
            puntaje += 30
            razones.append(f"✅ Patrón BAJISTA: {patron} ({fuerza_patron}%)")
            if direccion == "NEUTRAL":
                direccion = "SELL"
    
    # 6. Contexto (peso 20)
    if contexto_direccion == "FUERTE_ALCISTA":
        puntaje += 20
        razones.append("✅ Contexto: FUERTE ALCISTA")
        if direccion == "NEUTRAL":
            direccion = "BUY"
    elif contexto_direccion == "FUERTE_BAJISTA":
        puntaje += 20
        razones.append("✅ Contexto: FUERTE BAJISTA")
        if direccion == "NEUTRAL":
            direccion = "SELL"
    elif contexto_direccion == "ALCISTA":
        puntaje += 10
        razones.append("✅ Contexto: ALCISTA")
        if direccion == "NEUTRAL":
            direccion = "BUY"
    elif contexto_direccion == "BAJISTA":
        puntaje += 10
        razones.append("✅ Contexto: BAJISTA")
        if direccion == "NEUTRAL":
            direccion = "SELL"
    
    # 7. Normalizar puntaje (0-100)
    puntaje = min(puntaje, 100)
    
    return direccion, puntaje, razones

# ═══════════════════════════════════════════════════════════════
#  ESTRATEGIA 2: TENDENCIA INTELIGENTE (EMA + ADX + RSI)
# ═══════════════════════════════════════════════════════════════

def calcular_ema(prices, period):
    """Calcula EMA"""
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema

def calcular_rsi(prices, period=14):
    """Calcula RSI"""
    if len(prices) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
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

def calcular_adx(closes, period=14):
    """Calcula ADX simplificado"""
    if len(closes) < period + 1:
        return 0
    
    # Calcular +DM y -DM
    plus_dm = []
    minus_dm = []
    tr = []
    
    for i in range(1, len(closes)):
        up = closes[i] - closes[i-1]
        down = closes[i-1] - closes[i]
        
        if up > down and up > 0:
            plus_dm.append(up)
        else:
            plus_dm.append(0)
        
        if down > up and down > 0:
            minus_dm.append(down)
        else:
            minus_dm.append(0)
        
        # TR (verdadero rango) simplificado
        tr.append(abs(closes[i] - closes[i-1]))
    
    if len(tr) < period:
        return 0
    
    # ADX simplificado = media de (DI+ y DI-)
    di_plus = sum(plus_dm[-period:]) / (sum(tr[-period:]) or 1)
    di_minus = sum(minus_dm[-period:]) / (sum(tr[-period:]) or 1)
    dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
    
    return dx

def estrategia_tendencia_inteligente(candles):
    """
    ESTRATEGIA 2: Tendencia Inteligente (EMA + ADX + RSI)
    """
    if len(candles) < 50:
        return "NEUTRAL", 0, ["Datos insuficientes para Tendencia Inteligente"]
    
    razones = []
    closes = [c["close"] for c in candles]
    
    # 1. Calcular EMAs
    ema20 = calcular_ema(closes, PERIODO_EMA_RAPIDA)
    ema50 = calcular_ema(closes, PERIODO_EMA_MEDIA)
    ema200 = calcular_ema(closes, PERIODO_EMA_LENTA)
    
    if not ema20 or not ema50 or not ema200:
        return "NEUTRAL", 0, ["No se pudieron calcular EMAs"]
    
    # 2. Calcular RSI
    rsi = calcular_rsi(closes, PERIODO_RSI)
    
    # 3. Calcular ADX
    adx = calcular_adx(closes, PERIODO_ADX)
    
    # 4. Evaluar condiciones
    puntaje = 0
    direccion = "NEUTRAL"
    
    # Tendencia alcista
    if ema20 > ema50 > ema200:
        razones.append(f"✅ Tendencia ALCISTA (EMA20 > EMA50 > EMA200)")
        puntaje += 35
        if direccion == "NEUTRAL":
            direccion = "BUY"
    
    # Tendencia bajista
    elif ema20 < ema50 < ema200:
        razones.append(f"✅ Tendencia BAJISTA (EMA20 < EMA50 < EMA200)")
        puntaje += 35
        if direccion == "NEUTRAL":
            direccion = "SELL"
    
    # ADX fuerte
    if adx > 25:
        razones.append(f"✅ ADX: {adx:.1f} (Tendencia FUERTE)")
        puntaje += 25
    else:
        razones.append(f"⚠️ ADX: {adx:.1f} (Tendencia DÉBIL)")
        return "NEUTRAL", 0, ["ADX < 25 - Tendencia débil"]
    
    # RSI óptimo para BUY
    if direccion == "BUY" and 45 <= rsi <= 65:
        razones.append(f"✅ RSI: {rsi:.1f} (Óptimo para BUY)")
        puntaje += 40
    elif direccion == "BUY":
        razones.append(f"⚠️ RSI: {rsi:.1f} (Sub-óptimo para BUY)")
        puntaje += 10
    
    # RSI óptimo para SELL
    if direccion == "SELL" and 35 <= rsi <= 55:
        razones.append(f"✅ RSI: {rsi:.1f} (Óptimo para SELL)")
        puntaje += 40
    elif direccion == "SELL":
        razones.append(f"⚠️ RSI: {rsi:.1f} (Sub-óptimo para SELL)")
        puntaje += 10
    
    # Normalizar
    puntaje = min(puntaje, 100)
    
    return direccion, puntaje, razones

# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL v16.0 — ESTRATEGIA COMBINADA
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v16.0 — Estrategia Combinada
    
    50% Price Action + 50% Tendencia Inteligente
    Solo opera cuando ambas estrategias están alineadas
    Puntuación combinada >= 80
    """
    if len(candles) < 50:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["Datos insuficientes - necesita 50 velas"],
            "votos_buy": 0,
            "votos_sell": 0,
            "patrones_encontrados": 0,
            "pct_acierto": 0,
            "velas_analizadas": len(candles),
        }

    # ── ESTRATEGIA 1: PRICE ACTION ──────────────────────────────
    dir_pa, score_pa, razones_pa = estrategia_price_action(candles)
    
    # ── ESTRATEGIA 2: TENDENCIA INTELIGENTE ────────────────────
    dir_ti, score_ti, razones_ti = estrategia_tendencia_inteligente(candles)
    
    # ── COMBINAR ──────────────────────────────────────────────────
    razones = []
    puntaje_combinado = 0
    direccion = "ESPERAR"
    
    # Calcular puntaje combinado (50% cada una)
    if dir_pa != "NEUTRAL" and dir_ti != "NEUTRAL":
        if dir_pa == dir_ti:
            # ✅ AMBAS ESTRATEGIAS ALINEADAS
            direccion = dir_pa
            puntaje_combinado = (score_pa * 0.5) + (score_ti * 0.5)
            razones.append(f"🎯 AMBAS ESTRATEGIAS ALINEADAS → {direccion}")
            razones.append(f"📊 Price Action: {score_pa}%")
            razones.append(f"📊 Tendencia Inteligente: {score_ti}%")
            razones.append(f"📈 Puntaje combinado: {puntaje_combinado:.1f}%")
        else:
            # ❌ ESTRATEGIAS EN CONFLICTO
            razones.append("⚠️ ESTRATEGIAS EN CONFLICTO")
            razones.append(f"📊 Price Action: {dir_pa} ({score_pa}%)")
            razones.append(f"📊 Tendencia Inteligente: {dir_ti} ({score_ti}%)")
            razones.append("❌ No operar - Direcciones opuestas")
            direccion = "ESPERAR"
            puntaje_combinado = 0
    else:
        if dir_pa == "NEUTRAL":
            razones.append("⚠️ Price Action: Sin señal clara")
        if dir_ti == "NEUTRAL":
            razones.append("⚠️ Tendencia Inteligente: Sin señal clara")
        direccion = "ESPERAR"
        puntaje_combinado = 0
    
    # ── VERIFICAR PUNTAJE MÍNIMO ──────────────────────────────
    if puntaje_combinado >= PUNTAJE_MINIMO and direccion != "ESPERAR":
        # ✅ SEÑAL VÁLIDA
        razones.append(f"✅ PUNTAJE {puntaje_combinado:.1f}% ≥ {PUNTAJE_MINIMO}%")
        confianza = round(puntaje_combinado)
    else:
        if direccion != "ESPERAR":
            razones.append(f"❌ Puntaje {puntaje_combinado:.1f}% < {PUNTAJE_MINIMO}%")
        direccion = "ESPERAR"
        confianza = 0
    
    # ── INFORMACIÓN ADICIONAL ──────────────────────────────────
    # Añadir razones detalladas de cada estrategia
    for r in razones_pa[:3]:
        if r not in razones:
            razones.append(r)
    for r in razones_ti[:3]:
        if r not in razones:
            razones.append(r)

    return {
        "direccion": direccion,
        "confianza": confianza,
        "razones": razones[:8],
        "votos_buy": 1 if direccion == "BUY" else 0,
        "votos_sell": 1 if direccion == "SELL" else 0,
        "patrones_encontrados": 1 if direccion != "ESPERAR" else 0,
        "pct_acierto": confianza,
        "velas_analizadas": len(candles),
        "volatilidad": "media",
        "tendencia": "UP" if direccion == "BUY" else "DOWN" if direccion == "SELL" else "LATERAL",
        "score_price_action": score_pa,
        "score_tendencia_inteligente": score_ti,
        "puntaje_combinado": round(puntaje_combinado, 1),
        "direccion_pa": dir_pa,
        "direccion_ti": dir_ti,
        "indicadores": {
            "precio": round(candles[-1]["close"], 6),
            "score_pa": score_pa,
            "score_ti": score_ti,
            "puntaje_combinado": round(puntaje_combinado, 1),
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
    return "combinada", detectar_volatilidad(candles)

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
        if not candles or len(candles) < 50:
            continue
        try:
            senal = generar_senal(candles, "combinada", timeframe_seg)
            if senal["direccion"] in ("BUY", "SELL") and senal["confianza"] >= 80:
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
