"""
analysis.py v11.2 — CON VERIFICACIÓN EN TIEMPO REAL
- Genera señal SOLO si la vela actual CONFIRMA
- Verifica en tiempo real
- Cancela señales falsas
- Mayor precisión
"""

import math
import time

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

MIN_REPETICIONES = 3
CONFIANZA_MINIMA = 60
TOLERANCIA_COLOR = 1
VELAS_A_ANALIZAR = 300
MAX_VELAS_HISTORIAL = 300

# ═══════════════════════════════════════════════════════════════
#  CREAR FIRMA DE PATRÓN
# ═══════════════════════════════════════════════════════════════

def crear_firma_velas_rapida(candles, cantidad=5):
    if len(candles) < cantidad:
        return None
    
    colores = []
    tamanos = []
    
    for i in range(cantidad):
        vela = candles[-(i+1)]
        
        if vela["close"] > vela["open"]:
            colores.append("V")
        else:
            colores.append("R")
        
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
#  BUSCAR PATRONES
# ═══════════════════════════════════════════════════════════════

def buscar_patron_rapido(candles_historicas, patron_actual, profundidad=300):
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
        
        v1, v2, v3, v4, v5 = bloque[0], bloque[1], bloque[2], bloque[3], bloque[4]
        
        c1 = "V" if v1["close"] > v1["open"] else "R"
        c2 = "V" if v2["close"] > v2["open"] else "R"
        c3 = "V" if v3["close"] > v3["open"] else "R"
        c4 = "V" if v4["close"] > v4["open"] else "R"
        c5 = "V" if v5["close"] > v5["open"] else "R"
        colores = c1 + c2 + c3 + c4 + c5
        
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
        
        es_exacta = firma_completa == firma_buscar_completa
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

def analizar_resultados_rapido(resultados):
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
    
    pct_ganador = max(pct_up, pct_down)
    bonus_exactos = (exactos / total) * 10
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
#  VERIFICACIÓN EN TIEMPO REAL (NUEVO)
# ═══════════════════════════════════════════════════════════════

def verificar_vela_actual(candles, direccion_esperada):
    """
    Verifica si la vela ACTUAL sigue la dirección esperada
    """
    if len(candles) < 2:
        return False, 0, 0
    
    vela_actual = candles[-1]
    
    cuerpo = abs(vela_actual["close"] - vela_actual["open"])
    rango = vela_actual["high"] - vela_actual["low"]
    
    if rango < 0.00001:
        return False, 0, 0
    
    progreso = (vela_actual["close"] - vela_actual["open"]) / (vela_actual["high"] - vela_actual["low"] + 0.00001)
    
    if direccion_esperada == "BUY":
        if vela_actual["close"] > vela_actual["open"]:
            fuerza = (vela_actual["close"] - vela_actual["open"]) / vela_actual["open"] * 100
            return True, progreso, fuerza
        else:
            return False, progreso, 0
    
    elif direccion_esperada == "SELL":
        if vela_actual["close"] < vela_actual["open"]:
            fuerza = (vela_actual["open"] - vela_actual["close"]) / vela_actual["open"] * 100
            return True, progreso, fuerza
        else:
            return False, progreso, 0
    
    return False, 0, 0


def verificar_patron_en_vela_actual(candles):
    """
    Verifica si la vela actual sigue la tendencia de las anteriores
    """
    if len(candles) < 6:
        return False, "Sin suficientes datos"
    
    ultimas_5 = candles[-5:]
    
    # Verificar si la mayoría de las velas anteriores son del mismo color
    verdes = sum(1 for i in range(4) if ultimas_5[i]["close"] > ultimas_5[i]["open"])
    
    vela_actual = ultimas_5[-1]
    direccion_actual = "UP" if vela_actual["close"] > vela_actual["open"] else "DOWN"
    
    # Si 3+ de las 4 velas anteriores son VERDES y la actual es VERDE → confirmado
    if verdes >= 3 and direccion_actual == "UP":
        return True, "Tendencia alcista confirmada"
    
    # Si 3+ de las 4 velas anteriores son ROJAS y la actual es ROJA → confirmado
    if verdes <= 1 and direccion_actual == "DOWN":
        return True, "Tendencia bajista confirmada"
    
    return False, "La vela actual contradice la tendencia anterior"

# ═══════════════════════════════════════════════════════════════
#  INDICADORES RÁPIDOS
# ═══════════════════════════════════════════════════════════════

def ema_rapida(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val

def rsi_rapida(prices, period=14):
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
#  MOTOR PRINCIPAL v11.2 — CON VERIFICACIÓN
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v11.2 — CON VERIFICACIÓN EN TIEMPO REAL
    - Genera señal SOLO si la vela actual CONFIRMA
    - Cancela señales falsas
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
            "verificacion": False,
            "progreso_vela": 0,
        }

    closes = [c["close"] for c in candles[-VELAS_A_ANALIZAR:]]
    precio = closes[-1]

    # ── 1. CREAR FIRMA DEL PATRÓN ──────────────────────────────
    patron_actual = crear_firma_velas_rapida(candles, 5)
    if not patron_actual:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["No se pudo crear el patrón"],
            "patrones_encontrados": 0,
            "verificacion": False,
        }

    # ── 2. BUSCAR PATRONES ──────────────────────────────────────
    historial = candles[:-1]
    resultados = buscar_patron_rapido(historial, patron_actual, MAX_VELAS_HISTORIAL)
    analisis = analizar_resultados_rapido(resultados)

    # ── 3. INDICADORES ──────────────────────────────────────────
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

    # ── 4. DECISIÓN BASADA EN PATRÓN ──────────────────────────
    direccion_patron = "NEUTRAL"
    confianza_patron = 0
    
    if analisis["total"] >= MIN_REPETICIONES:
        if analisis["pct_up"] >= CONFIANZA_MINIMA:
            direccion_patron = "BUY"
            confianza_patron = analisis["confianza"]
        elif analisis["pct_down"] >= CONFIANZA_MINIMA:
            direccion_patron = "SELL"
            confianza_patron = analisis["confianza"]

    # ── 5. CONFIRMACIÓN CON INDICADORES ──────────────────────
    votos_buy = 0
    votos_sell = 0
    razones = []

    if direccion_patron == "BUY":
        votos_buy += 5
        razones.append(f"Patrón: {analisis['total']}x, {analisis['pct_up']}%")
    elif direccion_patron == "SELL":
        votos_sell += 5
        razones.append(f"Patrón: {analisis['total']}x, {analisis['pct_down']}%")

    if tendencia == "UP":
        votos_buy += 3
        razones.append(f"Tendencia UP ({fuerza_tendencia}%)")
    elif tendencia == "DOWN":
        votos_sell += 3
        razones.append(f"Tendencia DOWN ({fuerza_tendencia}%)")

    if rsi_val < 30:
        votos_buy += 2
        razones.append(f"RSI {round(rsi_val)} (sobrevendido)")
    elif rsi_val > 70:
        votos_sell += 2
        razones.append(f"RSI {round(rsi_val)} (sobrecomprado)")

    if ema_dir == "BUY":
        votos_buy += 2
        razones.append("EMA 5 > 20 (alcista)")
    elif ema_dir == "SELL":
        votos_sell += 2
        razones.append("EMA 5 < 20 (bajista)")

    # ── 6. DECISIÓN INICIAL ──────────────────────────────────────
    direccion = "ESPERAR"
    confianza = 0

    if votos_buy >= 5 and votos_buy > votos_sell * 1.3:
        direccion = "BUY"
        confianza = min(round((votos_buy / (votos_buy + votos_sell)) * 100), 98)
    elif votos_sell >= 5 and votos_sell > votos_buy * 1.3:
        direccion = "SELL"
        confianza = min(round((votos_sell / (votos_buy + votos_sell)) * 100), 98)

    # ── 7. VERIFICACIÓN EN TIEMPO REAL (NUEVO) ─────────────────
    if direccion in ("BUY", "SELL"):
        # Verificar vela actual
        es_valida, progreso, fuerza = verificar_vela_actual(candles, direccion)
        
        # Verificar patrón
        patron_valido, mensaje_patron = verificar_patron_en_vela_actual(candles)
        
        if es_valida and patron_valido:
            # ✅ CONFIRMADO
            confianza = min(confianza + 5, 98)
            razones.append(f"✅ Vela actual confirmada ({round(progreso*100)}%)")
            razones.append(f"✅ Fuerza: {round(fuerza, 4)}%")
            verificacion = True
        else:
            # ❌ CANCELADO
            direccion = "ESPERAR"
            confianza = 0
            razones = [
                f"Señal CANCELADA por falta de confirmación",
                f"Progreso vela: {round(progreso*100) if progreso else 0}%",
                f"Motivo: {mensaje_patron if not patron_valido else 'Vela no sigue dirección'}"
            ]
            verificacion = False
            fuerza = 0
    else:
        verificacion = False
        progreso = 0
        fuerza = 0

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
        "verificacion": verificacion,
        "progreso_vela": round(progreso * 100, 1) if progreso else 0,
        "fuerza_vela": round(fuerza, 4) if fuerza else 0,
        "indicadores": {
            "precio": round(precio, 6),
            "rsi": round(rsi_val, 1),
            "tendencia_fuerza": fuerza_tendencia,
            "patron_actual": patron_actual["firma_colores"],
        }
    }


# ═══════════════════════════════════════════════════════════════
#  COMPATIBILIDAD
# ═══════════════════════════════════════════════════════════════

def detectar_volatilidad(candles, periodo=14):
    return "media"

def seleccionar_estrategia_auto(candles):
    return "patrones_con_verificacion", "media"

def calcular_volatilidad_real(candles, periodo=14):
    return 0.0, "media"

def calcular_volatilidad_real_simple(candles, periodo=14):
    return 0.0
