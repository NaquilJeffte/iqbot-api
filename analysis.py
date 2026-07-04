"""
analysis.py v10.3 — BUSCADOR DE PATRONES MEJORADO
- Busca patrones SIMILARES (no solo idénticos)
- Acepta 1 vela de diferencia
- Mínimo 3 repeticiones para señal
- Confianza calculada con pesos
- Hasta 10000 velas analizadas
"""

import math
import time
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

MIN_REPETICIONES = 3       # Mínimo 3 repeticiones para señal
CONFIANZA_MINIMA = 60      # Mínimo 60% de acierto
TOLERANCIA_COLOR = 1       # 1 vela de diferencia permitida

# ═══════════════════════════════════════════════════════════════
#  CREAR FIRMA DE PATRÓN
# ═══════════════════════════════════════════════════════════════

def crear_firma_velas(candles, cantidad=5):
    """Crea firma de las últimas N velas"""
    if len(candles) < cantidad:
        return None
    
    # Colores: V (verde) / R (roja)
    colores = []
    # Tamaños: G (grande) / M (medio) / P (pequeño)
    tamanos = []
    # Sombras: S (superior) / I (inferior) / N (normal)
    sombras = []
    
    for i in range(cantidad):
        vela = candles[-(i+1)]
        
        # Color
        if vela["close"] > vela["open"]:
            colores.append("V")
        else:
            colores.append("R")
        
        # Tamaño del cuerpo
        cuerpo = abs(vela["close"] - vela["open"])
        rango = vela["high"] - vela["low"] if vela["high"] != vela["low"] else 0.00001
        
        if cuerpo / rango > 0.7:
            tamanos.append("G")
        elif cuerpo / rango > 0.3:
            tamanos.append("M")
        else:
            tamanos.append("P")
        
        # Sombra
        sombra_sup = vela["high"] - max(vela["close"], vela["open"])
        sombra_inf = min(vela["close"], vela["open"]) - vela["low"]
        
        if sombra_sup > sombra_inf * 2:
            sombras.append("S")  # Sombra superior larga (resistencia)
        elif sombra_inf > sombra_sup * 2:
            sombras.append("I")  # Sombra inferior larga (soporte)
        else:
            sombras.append("N")  # Normal
    
    return {
        "colores": "".join(colores),
        "tamanos": "".join(tamanos),
        "sombras": "".join(sombras),
        "firma_completa": "".join(colores) + "|" + "".join(tamanos) + "|" + "".join(sombras),
        "firma_colores": "".join(colores),
    }

# ═══════════════════════════════════════════════════════════════
#  BUSCAR PATRONES EN HISTORIAL
# ═══════════════════════════════════════════════════════════════

def buscar_patron_flexible(candles_historicas, patron_actual, profundidad=10000):
    """
    Busca patrones SIMILARES en el historial
    """
    if len(candles_historicas) < 10:
        return []
    
    resultados = []
    firma_buscar_colores = patron_actual["firma_colores"]
    firma_buscar_completa = patron_actual["firma_completa"]
    
    limite = min(len(candles_historicas) - 5, profundidad)
    
    for i in range(limite):
        bloque = candles_historicas[i:i+5]
        if len(bloque) < 5:
            continue
        
        firma_bloque = crear_firma_velas(bloque, 5)
        if not firma_bloque:
            continue
        
        # COINCIDENCIA EXACTA
        es_exacta = firma_bloque["firma_completa"] == firma_buscar_completa
        
        # COINCIDENCIA DE COLORES (permite 1 diferencia)
        coincidencia_colores = sum(1 for a, b in zip(firma_bloque["colores"], firma_buscar_colores) if a == b)
        es_similar = coincidencia_colores >= (5 - TOLERANCIA_COLOR)
        
        if es_exacta or es_similar:
            if i + 5 < len(candles_historicas):
                siguiente = candles_historicas[i+5]
                # Calcular cambio real
                cambio = (siguiente["close"] - siguiente["open"]) / siguiente["open"] * 100
                resultados.append({
                    "direccion": "UP" if siguiente["close"] > siguiente["open"] else "DOWN",
                    "cambio": cambio,
                    "exacto": es_exacta,
                    "coincidencia": coincidencia_colores,
                    "precio_entrada": siguiente["open"],
                    "precio_salida": siguiente["close"],
                })
    
    return resultados

# ═══════════════════════════════════════════════════════════════
#  ANALIZAR RESULTADOS
# ═══════════════════════════════════════════════════════════════

def analizar_resultados(resultados):
    """
    Analiza los resultados de la búsqueda de patrones
    """
    if not resultados:
        return {
            "total": 0,
            "up_count": 0,
            "down_count": 0,
            "pct_up": 0,
            "pct_down": 0,
            "cambio_promedio": 0,
            "exactos": 0,
            "similares": 0,
            "confianza": 0,
        }
    
    total = len(resultados)
    up_count = sum(1 for r in resultados if r["direccion"] == "UP")
    down_count = total - up_count
    exactos = sum(1 for r in resultados if r["exacto"])
    similares = total - exactos
    
    pct_up = (up_count / total) * 100
    pct_down = (down_count / total) * 100
    
    cambio_promedio = sum(r["cambio"] for r in resultados) / total
    
    # Confianza = % de acierto + bonus por exactos
    pct_ganador = max(pct_up, pct_down)
    bonus_exactos = (exactos / total) * 10  # Hasta +10% por exactos
    confianza = min(pct_ganador + bonus_exactos, 98)
    
    return {
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        "pct_up": round(pct_up, 1),
        "pct_down": round(pct_down, 1),
        "cambio_promedio": round(cambio_promedio, 3),
        "exactos": exactos,
        "similares": similares,
        "confianza": round(confianza, 1),
        "direccion_ganadora": "UP" if pct_up >= pct_down else "DOWN",
        "pct_ganador": round(pct_ganador, 1),
    }

# ═══════════════════════════════════════════════════════════════
#  INDICADORES DE CONFIRMACIÓN
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
    if slope_pct < 0.005:
        return "LATERAL", 0
    return ("UP" if slope > 0 else "DOWN"), round(slope_pct, 2)

# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL v10.3
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v10.3 — BUSCADOR DE PATRONES MEJORADO
    - Busca patrones SIMILARES (permite 1 diferencia)
    - Mínimo 3 repeticiones
    - Confianza con bonus por coincidencias exactas
    - Confirmación con indicadores
    """
    if len(candles) < 30:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["Datos insuficientes (necesita 30 velas)"],
            "votos_buy": 0,
            "votos_sell": 0,
            "patrones_encontrados": 0,
            "pct_acierto": 0,
        }

    closes = [c["close"] for c in candles]
    precio = closes[-1]

    # ── 1. CREAR FIRMA DEL PATRÓN ACTUAL ──────────────────────
    patron_actual = crear_firma_velas(candles, 5)
    if not patron_actual:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["No se pudo crear el patrón"],
            "patrones_encontrados": 0,
        }

    # ── 2. BUSCAR PATRONES SIMILARES ──────────────────────────
    resultados = buscar_patron_flexible(candles[:-1], patron_actual, 10000)
    
    # ── 3. ANALIZAR RESULTADOS ────────────────────────────────
    analisis = analizar_resultados(resultados)
    
    # ── 4. INDICADORES DE CONFIRMACIÓN ────────────────────────
    # Tendencia
    tendencia, fuerza_tendencia = tendencia_lineal(closes, 20)
    
    # RSI
    rsi_val = rsi(closes, 14)
    
    # EMA 5 vs 20
    ema5 = ema(closes, 5)
    ema20 = ema(closes, 20)
    ema_dir = "NEUTRAL"
    if ema5 and ema20:
        if ema5 > ema20:
            ema_dir = "BUY"
        else:
            ema_dir = "SELL"
    
    # ── 5. DECISIÓN BASADA EN PATRÓN ──────────────────────────
    direccion_patron = "NEUTRAL"
    confianza_patron = 0
    
    if analisis["total"] >= MIN_REPETICIONES:
        if analisis["pct_up"] >= CONFIANZA_MINIMA:
            direccion_patron = "BUY"
            confianza_patron = analisis["confianza"]
        elif analisis["pct_down"] >= CONFIANZA_MINIMA:
            direccion_patron = "SELL"
            confianza_patron = analisis["confianza"]
    
    # ── 6. CONFIRMACIÓN CON INDICADORES ──────────────────────
    votos_buy = 0
    votos_sell = 0
    razones = []
    
    # Voto del patrón (peso 5)
    if direccion_patron == "BUY":
        votos_buy += 5
        razones.append(f"Patrón REPETIDO: {analisis['total']} veces, {analisis['pct_up']}% acierto")
    elif direccion_patron == "SELL":
        votos_sell += 5
        razones.append(f"Patrón REPETIDO: {analisis['total']} veces, {analisis['pct_down']}% acierto")
    
    # Voto de tendencia (peso 3)
    if tendencia == "UP":
        votos_buy += 3
        razones.append(f"Tendencia ALCISTA (fuerza: {fuerza_tendencia}%)")
    elif tendencia == "DOWN":
        votos_sell += 3
        razones.append(f"Tendencia BAJISTA (fuerza: {fuerza_tendencia}%)")
    
    # Voto de RSI (peso 2)
    if rsi_val < 30:
        votos_buy += 2
        razones.append(f"RSI sobrevendido: {round(rsi_val)}%")
    elif rsi_val > 70:
        votos_sell += 2
        razones.append(f"RSI sobrecomprado: {round(rsi_val)}%")
    
    # Voto de EMA (peso 2)
    if ema_dir == "BUY":
        votos_buy += 2
        razones.append("EMA 5 > EMA 20 (alcista)")
    elif ema_dir == "SELL":
        votos_sell += 2
        razones.append("EMA 5 < EMA 20 (bajista)")
    
    # ── 7. DECISIÓN FINAL ──────────────────────────────────────
    if votos_buy >= 5 and votos_buy > votos_sell * 1.3:
        direccion = "BUY"
        confianza = min(round((votos_buy / (votos_buy + votos_sell)) * 100), 98)
    elif votos_sell >= 5 and votos_sell > votos_buy * 1.3:
        direccion = "SELL"
        confianza = min(round((votos_sell / (votos_buy + votos_sell)) * 100), 98)
    else:
        direccion = "ESPERAR"
        confianza = 0
        razones = ["No hay confirmación suficiente para BUY/SELL"]

    return {
        "direccion": direccion,
        "confianza": confianza,
        "razones": razones[:5],
        "votos_buy": votos_buy,
        "votos_sell": votos_sell,
        "score_buy": votos_buy,
        "score_sell": votos_sell,
        "patrones_encontrados": analisis["total"],
        "pct_acierto": analisis["pct_ganador"] if analisis["total"] > 0 else 0,
        "cambio_promedio": analisis["cambio_promedio"] if analisis["total"] > 0 else 0,
        "exactos": analisis["exactos"] if analisis["total"] > 0 else 0,
        "similares": analisis["similares"] if analisis["total"] > 0 else 0,
        "volatilidad": "media",
        "tendencia": tendencia,
        "indicadores": {
            "precio": round(precio, 6),
            "rsi": round(rsi_val, 1),
            "tendencia_fuerza": fuerza_tendencia,
            "total_velas": len(candles),
            "patron_actual": patron_actual["firma_colores"],
        }
    }


# ═══════════════════════════════════════════════════════════════
#  COMPATIBILIDAD
# ═══════════════════════════════════════════════════════════════

def detectar_volatilidad(candles, periodo=14):
    return "media"

def seleccionar_estrategia_auto(candles):
    return "patrones", "media"

def calcular_volatilidad_real(candles, periodo=14):
    return 0.0, "media"

def calcular_volatilidad_real_simple(candles, periodo=14):
    return 0.0
