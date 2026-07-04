"""
analysis.py v11.1 — BUSCADOR DE PATRONES OPTIMIZADO
- Optimizado para escaneo RÁPIDO de TODOS los activos
- Busca patrones SIMILARES (permite 1 diferencia)
- Mínimo 3 repeticiones para señal
- Confianza calculada con pesos
- Rápido y eficiente para escanear 200+ activos
"""

import math
import time
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN RÁPIDA (optimizada para escaneo)
# ═══════════════════════════════════════════════════════════════

MIN_REPETICIONES = 3       # Mínimo 3 repeticiones para señal
CONFIANZA_MINIMA = 60      # Mínimo 60% de acierto
TOLERANCIA_COLOR = 1       # 1 vela de diferencia permitida
VELAS_A_ANALIZAR = 300     # Velas por activo (balance velocidad/precisión)
MAX_VELAS_HISTORIAL = 300  # Máximo de velas para buscar patrones

# ═══════════════════════════════════════════════════════════════
#  CREAR FIRMA DE PATRÓN (RÁPIDO)
# ═══════════════════════════════════════════════════════════════

def crear_firma_velas_rapida(candles, cantidad=5):
    """Crea firma rápida de las últimas N velas (optimizada)"""
    if len(candles) < cantidad:
        return None
    
    colores = []
    tamanos = []
    
    for i in range(cantidad):
        vela = candles[-(i+1)]
        
        # Color (rápido)
        if vela["close"] > vela["open"]:
            colores.append("V")
        else:
            colores.append("R")
        
        # Tamaño (rápido)
        cuerpo = abs(vela["close"] - vela["open"])
        rango = vela["high"] - vela["low"] if vela["high"] != vela["low"] else 0.00001
        
        if cuerpo / rango > 0.7:
            tamanos.append("G")
        elif cuerpo / rango > 0.3:
            tamanos.append("M")
        else:
            tamanos.append("P")
    
    return {
        "colores": "".join(colores),
        "tamanos": "".join(tamanos),
        "firma_completa": "".join(colores) + "|" + "".join(tamanos),
        "firma_colores": "".join(colores),
    }

# ═══════════════════════════════════════════════════════════════
#  BUSCAR PATRONES (OPTIMIZADO PARA ESCANEO)
# ═══════════════════════════════════════════════════════════════

def buscar_patron_rapido(candles_historicas, patron_actual, profundidad=300):
    """
    Busca patrones SIMILARES (optimizado para velocidad)
    """
    if len(candles_historicas) < 10:
        return []
    
    resultados = []
    firma_buscar_colores = patron_actual["firma_colores"]
    firma_buscar_completa = patron_actual["firma_completa"]
    
    limite = min(len(candles_historicas) - 5, profundidad)
    
    # Búsqueda eficiente
    for i in range(limite):
        bloque = candles_historicas[i:i+5]
        if len(bloque) < 5:
            continue
        
        # Crear firma del bloque
        v1, v2, v3, v4, v5 = bloque[0], bloque[1], bloque[2], bloque[3], bloque[4]
        
        # Colores
        c1 = "V" if v1["close"] > v1["open"] else "R"
        c2 = "V" if v2["close"] > v2["open"] else "R"
        c3 = "V" if v3["close"] > v3["open"] else "R"
        c4 = "V" if v4["close"] > v4["open"] else "R"
        c5 = "V" if v5["close"] > v5["open"] else "R"
        
        colores = c1 + c2 + c3 + c4 + c5
        
        # Tamaños
        def get_size(vela):
            cuerpo = abs(vela["close"] - vela["open"])
            rango = vela["high"] - vela["low"] if vela["high"] != vela["low"] else 0.00001
            if cuerpo / rango > 0.7:
                return "G"
            elif cuerpo / rango > 0.3:
                return "M"
            return "P"
        
        t1, t2, t3, t4, t5 = get_size(v1), get_size(v2), get_size(v3), get_size(v4), get_size(v5)
        tamanos = t1 + t2 + t3 + t4 + t5
        
        firma_completa = colores + "|" + tamanos
        
        # COINCIDENCIA EXACTA
        es_exacta = firma_completa == firma_buscar_completa
        
        # COINCIDENCIA DE COLORES (permite 1 diferencia)
        coincidencia_colores = sum(1 for a, b in zip(colores, firma_buscar_colores) if a == b)
        es_similar = coincidencia_colores >= (5 - TOLERANCIA_COLOR)
        
        if es_exacta or es_similar:
            if i + 5 < len(candles_historicas):
                siguiente = candles_historicas[i+5]
                cambio = (siguiente["close"] - siguiente["open"]) / siguiente["open"] * 100
                resultados.append({
                    "direccion": "UP" if siguiente["close"] > siguiente["open"] else "DOWN",
                    "cambio": cambio,
                    "exacto": es_exacta,
                    "coincidencia": coincidencia_colores,
                })
    
    return resultados

# ═══════════════════════════════════════════════════════════════
#  ANALIZAR RESULTADOS (RÁPIDO)
# ═══════════════════════════════════════════════════════════════

def analizar_resultados_rapido(resultados):
    """
    Analiza resultados (optimizado para velocidad)
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
    up_count = 0
    down_count = 0
    exactos = 0
    suma_cambios = 0
    
    for r in resultados:
        if r["direccion"] == "UP":
            up_count += 1
        else:
            down_count += 1
        if r["exacto"]:
            exactos += 1
        suma_cambios += r["cambio"]
    
    similares = total - exactos
    pct_up = (up_count / total) * 100
    pct_down = (down_count / total) * 100
    cambio_promedio = suma_cambios / total if total > 0 else 0
    
    # Confianza = % de acierto + bonus por exactos
    pct_ganador = max(pct_up, pct_down)
    bonus_exactos = (exactos / total) * 10 if total > 0 else 0
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
#  INDICADORES DE CONFIRMACIÓN (RÁPIDOS)
# ═══════════════════════════════════════════════════════════════

def ema_rapida(prices, period):
    """EMA rápido"""
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val

def rsi_rapida(prices, period=14):
    """RSI rápido"""
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

def tendencia_rapida(closes, ventana=20):
    """Tendencia rápida"""
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
#  MOTOR PRINCIPAL v11.1 — OPTIMIZADO PARA ESCANEO
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v11.1 — Optimizado para escaneo rápido de TODOS los activos
    - Busca patrones SIMILARES (permite 1 diferencia)
    - Mínimo 3 repeticiones
    - Confianza con bonus por coincidencias exactas
    - Confirmación con indicadores rápidos
    """
    if len(candles) < 30:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["Datos insuficientes"],
            "votos_buy": 0,
            "votos_sell": 0,
            "patrones_encontrados": 0,
            "pct_acierto": 0,
        }

    # Usar solo las últimas velas para velocidad
    closes = [c["close"] for c in candles[-VELAS_A_ANALIZAR:]]
    precio = closes[-1]

    # ── 1. CREAR FIRMA DEL PATRÓN ACTUAL ──────────────────────
    patron_actual = crear_firma_velas_rapida(candles, 5)
    if not patron_actual:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["No se pudo crear el patrón"],
            "patrones_encontrados": 0,
        }

    # ── 2. BUSCAR PATRONES EN HISTORIAL ────────────────────────
    historial = candles[:-1]  # Excluir la vela actual
    resultados = buscar_patron_rapido(historial, patron_actual, MAX_VELAS_HISTORIAL)
    
    # ── 3. ANALIZAR RESULTADOS ────────────────────────────────
    analisis = analizar_resultados_rapido(resultados)
    
    # ── 4. INDICADORES DE CONFIRMACIÓN (rápidos) ─────────────
    tendencia, fuerza_tendencia = tendencia_rapida(closes, 20)
    rsi_val = rsi_rapida(closes, 14)
    
    ema5 = ema_rapida(closes, 5)
    ema20 = ema_rapida(closes, 20)
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
        razones.append(f"Patrón: {analisis['total']}x, {analisis['pct_up']}%")
    elif direccion_patron == "SELL":
        votos_sell += 5
        razones.append(f"Patrón: {analisis['total']}x, {analisis['pct_down']}%")
    
    # Voto de tendencia (peso 3)
    if tendencia == "UP":
        votos_buy += 3
        razones.append(f"Tendencia UP ({fuerza_tendencia}%)")
    elif tendencia == "DOWN":
        votos_sell += 3
        razones.append(f"Tendencia DOWN ({fuerza_tendencia}%)")
    
    # Voto de RSI (peso 2)
    if rsi_val < 30:
        votos_buy += 2
        razones.append(f"RSI {round(rsi_val)} (sobrevendido)")
    elif rsi_val > 70:
        votos_sell += 2
        razones.append(f"RSI {round(rsi_val)} (sobrecomprado)")
    
    # Voto de EMA (peso 2)
    if ema_dir == "BUY":
        votos_buy += 2
        razones.append("EMA 5 > 20 (alcista)")
    elif ema_dir == "SELL":
        votos_sell += 2
        razones.append("EMA 5 < 20 (bajista)")
    
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
        razones = ["Sin confirmación suficiente"]

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
    return "patrones_rapidos", "media"

def calcular_volatilidad_real(candles, periodo=14):
    return 0.0, "media"

def calcular_volatilidad_real_simple(candles, periodo=14):
    return 0.0
