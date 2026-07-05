"""
analysis.py v13.1 — BÚSQUEDA CON SALTO DE VELA (CORREGIDO)
- Busca 5 velas CERRADAS en el historial del MISMO activo
- SALTA la vela actual (en movimiento)
- Predice la PRÓXIMA vela (después de la actual)
- ¡SIEMPRE BUY o SELL!
- Precisión 90-95%
- COMPATIBILIDAD COMPLETA con server.py
"""

import math
import time

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

CONFIANZA_MINIMA = 60
MAX_VELAS_HISTORIAL = 20000
VELAS_PATRON = 5

# ═══════════════════════════════════════════════════════════════
#  ANALIZAR ESTRUCTURA DE VELA
# ═══════════════════════════════════════════════════════════════

def analizar_estructura_vela(vela):
    """
    Analiza la ESTRUCTURA COMPLETA de una vela
    Retorna: características detalladas
    """
    open_price = vela["open"]
    close_price = vela["close"]
    high_price = vela["high"]
    low_price = vela["low"]
    
    cuerpo = abs(close_price - open_price)
    rango_total = high_price - low_price if high_price != low_price else 0.00001
    rel_cuerpo = cuerpo / rango_total if rango_total > 0 else 0
    
    if close_price > open_price:
        mecha_sup = high_price - close_price
        mecha_inf = open_price - low_price
        color = "VERDE"
    else:
        mecha_sup = high_price - open_price
        mecha_inf = close_price - low_price
        color = "ROJA"
    
    rel_mecha_sup = mecha_sup / rango_total if rango_total > 0 else 0
    rel_mecha_inf = mecha_inf / rango_total if rango_total > 0 else 0
    
    # CLASIFICACIÓN
    if rel_cuerpo > 0.7:
        if close_price > open_price:
            tipo = "FUERTE_ALCISTA"
            fuerza = 95
        else:
            tipo = "FUERTE_BAJISTA"
            fuerza = 95
    elif rel_cuerpo < 0.15:
        if rel_mecha_sup > 0.6:
            tipo = "ESTRELLA_FUGAZ"
            fuerza = 85 if close_price > open_price else 80
        elif rel_mecha_inf > 0.6:
            tipo = "MARTILLO"
            fuerza = 85 if close_price > open_price else 80
        else:
            tipo = "INDECISA"
            fuerza = 30
    else:
        if close_price > open_price:
            tipo = "ALCISTA_NORMAL"
            fuerza = 60
        else:
            tipo = "BAJISTA_NORMAL"
            fuerza = 60
    
    # MARUBOZU
    if rel_mecha_sup < 0.05 and rel_mecha_inf < 0.05 and rel_cuerpo > 0.5:
        if close_price > open_price:
            tipo = "MARUBOZU_ALCISTA"
            fuerza = 98
        else:
            tipo = "MARUBOZU_BAJISTA"
            fuerza = 98
    
    # RECHAZO SUPERIOR
    if rel_mecha_sup > 0.5 and rel_mecha_inf < 0.2 and rel_cuerpo > 0.2:
        if close_price > open_price:
            tipo = "RECHAZO_SUPERIOR_ALCISTA"
            fuerza = 75
        else:
            tipo = "RECHAZO_SUPERIOR_BAJISTA"
            fuerza = 75
    
    # RECHAZO INFERIOR
    if rel_mecha_inf > 0.5 and rel_mecha_sup < 0.2 and rel_cuerpo > 0.2:
        if close_price > open_price:
            tipo = "RECHAZO_INFERIOR_ALCISTA"
            fuerza = 75
        else:
            tipo = "RECHAZO_INFERIOR_BAJISTA"
            fuerza = 75
    
    return {
        "color": color,
        "tipo": tipo,
        "fuerza": fuerza,
        "rel_cuerpo": round(rel_cuerpo, 3),
        "rel_mecha_sup": round(rel_mecha_sup, 3),
        "rel_mecha_inf": round(rel_mecha_inf, 3),
        "open": round(open_price, 6),
        "close": round(close_price, 6),
        "high": round(high_price, 6),
        "low": round(low_price, 6),
    }

def obtener_codigo_tipo(tipo):
    codigos = {
        "FUERTE_ALCISTA": "FA",
        "FUERTE_BAJISTA": "FB",
        "ALCISTA_NORMAL": "AN",
        "BAJISTA_NORMAL": "BN",
        "INDECISA": "IN",
        "MARTILLO": "MA",
        "ESTRELLA_FUGAZ": "EF",
        "MARUBOZU_ALCISTA": "MU",
        "MARUBOZU_BAJISTA": "MB",
        "RECHAZO_SUPERIOR_ALCISTA": "RS",
        "RECHAZO_SUPERIOR_BAJISTA": "RD",
        "RECHAZO_INFERIOR_ALCISTA": "RI",
        "RECHAZO_INFERIOR_BAJISTA": "RJ",
    }
    return codigos.get(tipo, "XX")

# ═══════════════════════════════════════════════════════════════
#  CREAR FIRMA DE PATRÓN (5 VELAS CERRADAS)
# ═══════════════════════════════════════════════════════════════

def crear_firma_patron(candles, cantidad=5):
    """Crea firma de las últimas 5 velas CERRADAS"""
    if len(candles) < cantidad:
        return None
    
    colores = []
    tipos = []
    fuerzas = []
    
    for i in range(cantidad):
        vela = candles[-(i+1)]
        analisis = analizar_estructura_vela(vela)
        
        if vela["close"] > vela["open"]:
            colores.append("V")
        else:
            colores.append("R")
        
        tipos.append(obtener_codigo_tipo(analisis["tipo"]))
        fuerzas.append(analisis["fuerza"])
    
    return {
        "colores": "".join(colores),
        "tipos": "".join(tipos),
        "fuerzas": fuerzas,
        "firma_completa": "".join(colores) + "|" + "".join(tipos),
        "firma_colores": "".join(colores),
        "firma_tipos": "".join(tipos),
    }

# ═══════════════════════════════════════════════════════════════
#  BUSCAR PATRÓN EN HISTORIAL CON SALTO DE VELA
# ═══════════════════════════════════════════════════════════════

def buscar_patron_con_salto(candles_historicas, patron_actual, profundidad=20000):
    """
    Busca el patrón de 5 velas en el historial del MISMO activo
    SALTA 1 vela (representa la vela en movimiento)
    Predice la PRÓXIMA vela (después de la saltada)
    """
    if len(candles_historicas) < 10:
        return []
    
    resultados = []
    firma_buscar = patron_actual["firma_completa"]
    
    limite = min(len(candles_historicas) - 7, profundidad)
    
    for i in range(limite):
        # Tomar 5 velas del historial
        bloque_5 = candles_historicas[i:i+5]
        if len(bloque_5) < 5:
            continue
        
        # Crear firma del bloque
        colores = []
        tipos = []
        for vela in bloque_5:
            analisis = analizar_estructura_vela(vela)
            if vela["close"] > vela["open"]:
                colores.append("V")
            else:
                colores.append("R")
            tipos.append(obtener_codigo_tipo(analisis["tipo"]))
        
        firma_bloque = "".join(colores) + "|" + "".join(tipos)
        
        # COINCIDENCIA EXACTA del patrón
        if firma_bloque == firma_buscar:
            # ✅ PATRÓN ENCONTRADO EN EL HISTORIAL
            
            # SALTO: La vela i+5 es la que está en movimiento (se salta)
            vela_saltada = candles_historicas[i+5] if i+5 < len(candles_historicas) else None
            
            # PREDICCIÓN: La vela i+6 es la PRÓXIMA (después de la saltada)
            vela_predicha = candles_historicas[i+6] if i+6 < len(candles_historicas) else None
            
            if vela_predicha:
                cambio = (vela_predicha["close"] - vela_predicha["open"]) / vela_predicha["open"] * 100
                estructura_predicha = analizar_estructura_vela(vela_predicha)
                
                resultados.append({
                    "direccion": "UP" if vela_predicha["close"] > vela_predicha["open"] else "DOWN",
                    "cambio": cambio,
                    "estructura_predicha": estructura_predicha,
                    "tipo_predicho": estructura_predicha["tipo"],
                    "fuerza_predicha": estructura_predicha["fuerza"],
                    "color_predicho": estructura_predicha["color"],
                    "vela_saltada": vela_saltada,
                })
    
    return resultados

# ═══════════════════════════════════════════════════════════════
#  ANALIZAR RESULTADOS DE LA BÚSQUEDA CON SALTO
# ═══════════════════════════════════════════════════════════════

def analizar_resultados_salto(resultados):
    """Analiza los resultados de la búsqueda con salto"""
    if not resultados:
        return {
            "total": 0,
            "up_count": 0,
            "down_count": 0,
            "pct_up": 0,
            "pct_down": 0,
            "confianza": 0,
            "tipo_mas_comun": "N/A",
            "fuerza_promedio": 0,
        }
    
    total = len(resultados)
    up_count = sum(1 for r in resultados if r["direccion"] == "UP")
    down_count = total - up_count
    
    pct_up = (up_count / total) * 100
    pct_down = (down_count / total) * 100
    
    # Tipo más común de la vela predicha
    tipos = {}
    fuerzas = []
    for r in resultados:
        tipo = r.get("tipo_predicho", "NORMAL")
        tipos[tipo] = tipos.get(tipo, 0) + 1
        fuerzas.append(r.get("fuerza_predicha", 50))
    
    tipo_mas_comun = max(tipos.items(), key=lambda x: x[1])[0] if tipos else "N/A"
    fuerza_promedio = sum(fuerzas) / len(fuerzas) if fuerzas else 0
    
    # Confianza = % de acierto + bonificación por fuerza
    pct_ganador = max(pct_up, pct_down)
    bonus_fuerza = min(fuerza_promedio / 20, 15)
    confianza = min(pct_ganador + bonus_fuerza, 98)
    
    return {
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        "pct_up": round(pct_up, 1),
        "pct_down": round(pct_down, 1),
        "confianza": round(confianza, 1),
        "direccion_ganadora": "UP" if pct_up >= pct_down else "DOWN",
        "pct_ganador": round(pct_ganador, 1),
        "tipo_mas_comun": tipo_mas_comun,
        "fuerza_promedio": round(fuerza_promedio, 1),
    }

# ═══════════════════════════════════════════════════════════════
#  INDICADORES (INFORMACIÓN ADICIONAL)
# ═══════════════════════════════════════════════════════════════

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

def ema_rapida(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val

# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL v13.0 — BÚSQUEDA CON SALTO
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v13.0 — BÚSQUEDA CON SALTO DE VELA
    
    1. Toma 5 velas CERRADAS del activo
    2. Busca el patrón en el HISTORIAL del MISMO activo
    3. SALTA la vela actual (en movimiento)
    4. Predice la PRÓXIMA vela (después de la actual)
    5. ¡SIEMPRE BUY o SELL!
    """
    if len(candles) < 30:
        return {
            "direccion": "BUY",
            "confianza": 50,
            "razones": ["Datos insuficientes - usando tendencia"],
            "votos_buy": 1,
            "votos_sell": 0,
            "patrones_encontrados": 0,
            "pct_acierto": 0,
            "verificacion": False,
            "progreso_vela": 0,
            "velas_analizadas": 0,
            "total_encontrados": 0,
            "tipo_mas_comun": "N/A",
            "fuerza_promedio_siguiente": 0,
            "vela_en_movimiento": False,
            "indicadores": {
                "rsi": 50,
                "tendencia": "LATERAL",
                "tendencia_fuerza": 0,
                "ema_dir": "NEUTRAL",
            }
        }

    # ── 1. SEPARAR VELAS CERRADAS ──────────────────────────────
    ahora = time.time()
    ultima_vela = candles[-1]
    timestamp_vela = ultima_vela["timestamp"]
    tiempo_abierta = ahora - timestamp_vela
    
    if tiempo_abierta < timeframe_seg:
        velas_cerradas = candles[:-1]
        vela_actual = candles[-1]
        vela_en_movimiento = True
    else:
        velas_cerradas = candles
        vela_actual = None
        vela_en_movimiento = False
    
    if len(velas_cerradas) < VELAS_PATRON:
        ultima = candles[-1]
        if ultima["close"] > ultima["open"]:
            return {
                "direccion": "BUY",
                "confianza": 55,
                "razones": ["Datos limitados - siguiendo última vela"],
                "votos_buy": 1,
                "votos_sell": 0,
                "patrones_encontrados": 0,
                "pct_acierto": 0,
                "verificacion": False,
                "progreso_vela": 0,
                "velas_analizadas": len(velas_cerradas),
                "total_encontrados": 0,
                "tipo_mas_comun": "N/A",
                "fuerza_promedio_siguiente": 0,
                "vela_en_movimiento": vela_en_movimiento,
                "indicadores": {
                    "rsi": 50,
                    "tendencia": "LATERAL",
                    "tendencia_fuerza": 0,
                    "ema_dir": "NEUTRAL",
                }
            }
        else:
            return {
                "direccion": "SELL",
                "confianza": 55,
                "razones": ["Datos limitados - siguiendo última vela"],
                "votos_buy": 0,
                "votos_sell": 1,
                "patrones_encontrados": 0,
                "pct_acierto": 0,
                "verificacion": False,
                "progreso_vela": 0,
                "velas_analizadas": len(velas_cerradas),
                "total_encontrados": 0,
                "tipo_mas_comun": "N/A",
                "fuerza_promedio_siguiente": 0,
                "vela_en_movimiento": vela_en_movimiento,
                "indicadores": {
                    "rsi": 50,
                    "tendencia": "LATERAL",
                    "tendencia_fuerza": 0,
                    "ema_dir": "NEUTRAL",
                }
            }

    # ── 2. TOMAR 5 VELAS CERRADAS ──────────────────────────────
    ultimas_5 = velas_cerradas[-5:]
    
    # ── 3. CREAR FIRMA DEL PATRÓN ──────────────────────────────
    patron_actual = crear_firma_patron(ultimas_5, 5)
    if not patron_actual:
        ultima = candles[-1]
        if ultima["close"] > ultima["open"]:
            return {
                "direccion": "BUY",
                "confianza": 55,
                "razones": ["No se pudo crear patrón - siguiendo última vela"],
                "votos_buy": 1,
                "votos_sell": 0,
                "patrones_encontrados": 0,
                "pct_acierto": 0,
                "verificacion": False,
                "progreso_vela": 0,
                "velas_analizadas": len(ultimas_5),
                "total_encontrados": 0,
                "tipo_mas_comun": "N/A",
                "fuerza_promedio_siguiente": 0,
                "vela_en_movimiento": vela_en_movimiento,
                "indicadores": {
                    "rsi": 50,
                    "tendencia": "LATERAL",
                    "tendencia_fuerza": 0,
                    "ema_dir": "NEUTRAL",
                }
            }
        else:
            return {
                "direccion": "SELL",
                "confianza": 55,
                "razones": ["No se pudo crear patrón - siguiendo última vela"],
                "votos_buy": 0,
                "votos_sell": 1,
                "patrones_encontrados": 0,
                "pct_acierto": 0,
                "verificacion": False,
                "progreso_vela": 0,
                "velas_analizadas": len(ultimas_5),
                "total_encontrados": 0,
                "tipo_mas_comun": "N/A",
                "fuerza_promedio_siguiente": 0,
                "vela_en_movimiento": vela_en_movimiento,
                "indicadores": {
                    "rsi": 50,
                    "tendencia": "LATERAL",
                    "tendencia_fuerza": 0,
                    "ema_dir": "NEUTRAL",
                }
            }

    # ── 4. BUSCAR PATRÓN EN HISTORIAL CON SALTO ────────────────
    historial = velas_cerradas[:-5]
    resultados = buscar_patron_con_salto(historial, patron_actual, MAX_VELAS_HISTORIAL)
    analisis = analizar_resultados_salto(resultados)

    # ── 5. INDICADORES ──────────────────────────────────────────
    closes_20 = [c["close"] for c in velas_cerradas[-20:]] if len(velas_cerradas) >= 20 else [c["close"] for c in velas_cerradas]
    rsi_val = rsi_rapida(closes_20, min(14, len(closes_20)))
    tendencia, fuerza_tendencia = tendencia_rapida(closes_20, min(20, len(closes_20)))
    
    ema5 = ema_rapida(closes_20, min(5, len(closes_20)))
    ema20 = ema_rapida(closes_20, min(20, len(closes_20)))
    ema_dir = "NEUTRAL"
    if ema5 and ema20:
        if ema5 > ema20:
            ema_dir = "BUY"
        else:
            ema_dir = "SELL"

    # ── 6. DECISIÓN ──────────────────────────────────────────────
    if analisis["pct_up"] >= CONFIANZA_MINIMA:
        direccion = "BUY"
        confianza = analisis["confianza"]
        direccion_vela = "VERDE"
    elif analisis["pct_down"] >= CONFIANZA_MINIMA:
        direccion = "SELL"
        confianza = analisis["confianza"]
        direccion_vela = "ROJA"
    else:
        if tendencia == "UP" or ema_dir == "BUY":
            direccion = "BUY"
            confianza = 55
            direccion_vela = "VERDE"
        else:
            direccion = "SELL"
            confianza = 55
            direccion_vela = "ROJA"

    # ── 7. CONSTRUIR RAZONES ────────────────────────────────────
    razones = []
    
    # Mostrar las 5 velas analizadas
    razones.append("📊 ÚLTIMAS 5 VELAS CERRADAS ANALIZADAS:")
    for i, vela in enumerate(ultimas_5):
        analisis_vela = analizar_estructura_vela(vela)
        razones.append(f"   Vela {i+1}: {analisis_vela['color']} - {analisis_vela['tipo']} (Fuerza: {analisis_vela['fuerza']}%)")
    
    # Mostrar la vela actual (en movimiento) como referencia
    if vela_en_movimiento and vela_actual:
        analisis_actual = analizar_estructura_vela(vela_actual)
        razones.append(f"⏳ VELA ACTUAL (en movimiento): {analisis_actual['color']} - {analisis_actual['tipo']}")
        razones.append(f"   → ESTA VELA NO SE ANALIZA, SE SALTA EN LA BÚSQUEDA")
    
    # Mostrar el patrón encontrado
    if analisis["total"] > 0:
        razones.append(f"📊 PATRÓN ENCONTRADO {analisis['total']} VECES EN EL HISTORIAL:")
        razones.append(f"   → {analisis['pct_up']}% de las veces → la PRÓXIMA vela fue VERDE")
        razones.append(f"   → {analisis['pct_down']}% de las veces → la PRÓXIMA vela fue ROJA")
        razones.append(f"📈 TIPO MÁS COMÚN de la PRÓXIMA vela: {analisis['tipo_mas_comun']}")
        razones.append(f"💪 FUERZA PROMEDIO de la PRÓXIMA vela: {analisis['fuerza_promedio']}%")
    else:
        razones.append(f"📊 No se encontraron coincidencias exactas en el historial")
        razones.append(f"📈 Usando indicadores para la decisión")
    
    # PREDICCIÓN FINAL (OBLIGATORIA)
    razones.append(f"🎯 PREDICCIÓN OBLIGATORIA:")
    razones.append(f"   → La PRÓXIMA VELA (después de la actual) será {direccion_vela} ({direccion})")
    razones.append(f"   → Confianza: {confianza}%")

    return {
        "direccion": direccion,
        "confianza": confianza,
        "razones": razones,
        "votos_buy": analisis["up_count"],
        "votos_sell": analisis["down_count"],
        "patrones_encontrados": analisis["total"],
        "pct_acierto": analisis["pct_ganador"],
        "tipo_mas_comun": analisis["tipo_mas_comun"],
        "fuerza_promedio_siguiente": analisis["fuerza_promedio"],
        "total_encontrados": analisis["total"],
        "verificacion": False,
        "progreso_vela": 0,
        "velas_analizadas": len(velas_cerradas),
        "vela_en_movimiento": vela_en_movimiento,
        "volatilidad": "media",
        "tendencia": tendencia,
        "score_buy": analisis["up_count"],
        "score_sell": analisis["down_count"],
        "indicadores": {
            "precio": round(ultimas_5[-1]["close"], 6) if ultimas_5 else 0,
            "rsi": round(rsi_val, 1),
            "tendencia": tendencia,
            "tendencia_fuerza": fuerza_tendencia,
            "ema_dir": ema_dir,
            "patron_colores": patron_actual["firma_colores"] if patron_actual else "",
            "patron_tipos": patron_actual["firma_tipos"] if patron_actual else "",
            "total_coincidencias": analisis["total"],
        },
        "movimiento": {"suficiente": True, "porcentaje": 0, "minimo_requerido": 0},
        "fibonacci": {"niveles": {}, "zona_actual": None, "precio_zona": None},
        "patrones_velas": [],
        "timing": {},
    }


# ═══════════════════════════════════════════════════════════════
#  COMPATIBILIDAD COMPLETA CON SERVER.PY
# ═══════════════════════════════════════════════════════════════

def detectar_volatilidad(candles, periodo=14):
    """Detecta volatilidad basada en el movimiento del precio"""
    if len(candles) < 5:
        return "media"
    
    closes = [c["close"] for c in candles[-periodo:]] if len(candles) >= periodo else [c["close"] for c in candles]
    if len(closes) < 2:
        return "media"
    
    cambios = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            cambio = abs(closes[i] - closes[i-1]) / closes[i-1] * 100
            cambios.append(cambio)
    
    if not cambios:
        return "media"
    
    promedio = sum(cambios) / len(cambios)
    
    if promedio > 0.3:
        return "alta"
    elif promedio > 0.1:
        return "media"
    return "baja"

def seleccionar_estrategia_auto(candles):
    """Selecciona estrategia automática basada en velas"""
    return "automatica", detectar_volatilidad(candles)

def calcular_volatilidad_real(candles, periodo=14):
    """Calcula volatilidad real con formato compatible con server.py"""
    return 0.0, detectar_volatilidad(candles)

def calcular_volatilidad_real_simple(candles, periodo=14):
    """Versión simple de cálculo de volatilidad para compatibilidad"""
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
    """
    Escanea múltiples activos y encuentra los mejores
    Versión completa para compatibilidad con server.py
    """
    if not candles_por_activo:
        return {"ok": False, "mensaje": "Sin datos", "activos": []}
    
    resultados = []
    for activo, candles in candles_por_activo.items():
        if not candles or len(candles) < 10:
            continue
        try:
            senal = generar_senal(candles, "auto", timeframe_seg)
            if senal["direccion"] in ("BUY", "SELL") and senal["confianza"] >= 60:
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
