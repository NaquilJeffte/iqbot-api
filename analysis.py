"""
analysis.py v15.0 — PREDICCIÓN CON 1 VELA + 2 CONFIRMACIONES
- Analiza SOLO la última vela CERRADA
- Busca esa vela en el historial (1000 velas)
- CONFIRMA 2 VECES la coincidencia
- Predice cómo terminará la vela EN MOVIMIENTO
- ¡MÁS PRECISO!
"""

import math
import time

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

CONFIANZA_MINIMA = 60
MAX_VELAS_HISTORIAL = 1000
VELAS_PATRON = 1  # ✅ SOLO 1 VELA
CONFIRMACIONES_REQUERIDAS = 2  # ✅ REQUIERE 2 CONFIRMACIONES

# ═══════════════════════════════════════════════════════════════
#  ANALIZAR ESTRUCTURA DE VELA (COMPLETA)
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
        direccion = "UP"
    else:
        mecha_sup = high_price - open_price
        mecha_inf = close_price - low_price
        color = "ROJA"
        direccion = "DOWN"
    
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
        "direccion": direccion,
        "tipo": tipo,
        "fuerza": fuerza,
        "rel_cuerpo": round(rel_cuerpo, 3),
        "rel_mecha_sup": round(rel_mecha_sup, 3),
        "rel_mecha_inf": round(rel_mecha_inf, 3),
        "open": round(open_price, 6),
        "close": round(close_price, 6),
        "high": round(high_price, 6),
        "low": round(low_price, 6),
        "cuerpo": round(cuerpo, 6),
        "rango": round(rango_total, 6),
    }

def obtener_codigo_vela(vela):
    """Crea un código único para una vela basado en su estructura"""
    analisis = analizar_estructura_vela(vela)
    
    # Código: Color + Tipo + Fuerza + Relación de mechas
    color = "V" if analisis["color"] == "VERDE" else "R"
    
    codigos_tipo = {
        "FUERTE_ALCISTA": "FA", "FUERTE_BAJISTA": "FB",
        "ALCISTA_NORMAL": "AN", "BAJISTA_NORMAL": "BN",
        "INDECISA": "IN", "MARTILLO": "MA",
        "ESTRELLA_FUGAZ": "EF", "MARUBOZU_ALCISTA": "MU",
        "MARUBOZU_BAJISTA": "MB", "RECHAZO_SUPERIOR_ALCISTA": "RS",
        "RECHAZO_SUPERIOR_BAJISTA": "RD", "RECHAZO_INFERIOR_ALCISTA": "RI",
        "RECHAZO_INFERIOR_BAJISTA": "RJ",
    }
    tipo = codigos_tipo.get(analisis["tipo"], "XX")
    fuerza = round(analisis["fuerza"] / 10, 1)
    mecha = round((analisis["rel_mecha_sup"] + analisis["rel_mecha_inf"]) / 2, 2)
    
    return f"{color}{tipo}{fuerza}{mecha}"

# ═══════════════════════════════════════════════════════════════
#  BUSCAR VELA EN HISTORIAL (CON 2 CONFIRMACIONES)
# ═══════════════════════════════════════════════════════════════

def buscar_vela_con_confirmacion(candles_historicas, vela_actual, profundidad=1000):
    """
    Busca la vela actual en el historial
    REQUIERE 2 CONFIRMACIONES para dar señal
    """
    if len(candles_historicas) < 10:
        return []
    
    codigo_buscar = obtener_codigo_vela(vela_actual)
    resultados = []
    coincidencias = 0
    
    limite = min(len(candles_historicas) - 1, profundidad)
    
    for i in range(limite):
        vela_historial = candles_historicas[i]
        codigo_historial = obtener_codigo_vela(vela_historial)
        
        if codigo_historial == codigo_buscar:
            coincidencias += 1
            
            # Ver qué pasó DESPUÉS de esta vela
            if i + 1 < len(candles_historicas):
                siguiente = candles_historicas[i + 1]
                cambio = (siguiente["close"] - siguiente["open"]) / siguiente["open"] * 100
                estructura_siguiente = analizar_estructura_vela(siguiente)
                
                resultados.append({
                    "direccion": "UP" if siguiente["close"] > siguiente["open"] else "DOWN",
                    "cambio": cambio,
                    "estructura": estructura_siguiente,
                    "tipo": estructura_siguiente["tipo"],
                    "fuerza": estructura_siguiente["fuerza"],
                    "coincidencia": coincidencias,
                })
                
                # ✅ Si encontramos 2 confirmaciones, podemos parar
                if coincidencias >= CONFIRMACIONES_REQUERIDAS:
                    break
    
    return resultados

# ═══════════════════════════════════════════════════════════════
#  ANALIZAR RESULTADOS
# ═══════════════════════════════════════════════════════════════

def analizar_resultados_vela(resultados):
    """Analiza los resultados de la búsqueda de vela con confirmación"""
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
            "confirmaciones": 0,
            "confirmado": False,
        }
    
    total = len(resultados)
    up_count = sum(1 for r in resultados if r["direccion"] == "UP")
    down_count = total - up_count
    
    pct_up = (up_count / total) * 100
    pct_down = (down_count / total) * 100
    
    tipos = {}
    fuerzas = []
    for r in resultados:
        tipo = r.get("tipo", "NORMAL")
        tipos[tipo] = tipos.get(tipo, 0) + 1
        fuerzas.append(r.get("fuerza", 50))
    
    tipo_mas_comun = max(tipos.items(), key=lambda x: x[1])[0] if tipos else "N/A"
    fuerza_promedio = sum(fuerzas) / len(fuerzas) if fuerzas else 0
    
    # Confianza = % de acierto + bonificación por fuerza
    pct_ganador = max(pct_up, pct_down)
    bonus_fuerza = min(fuerza_promedio / 20, 15)
    confianza = min(pct_ganador + bonus_fuerza, 98)
    
    # Verificar si se cumplieron las 2 confirmaciones
    confirmado = total >= CONFIRMACIONES_REQUERIDAS
    
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
        "confirmaciones": total,
        "confirmado": confirmado,
    }

# ═══════════════════════════════════════════════════════════════
#  INDICADORES (CONFIRMACIÓN ADICIONAL)
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

# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL v15.0 — 1 VELA + 2 CONFIRMACIONES
# ═══════════════════════════════════════════════════════════════

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v15.0 — PREDICCIÓN CON 1 VELA + 2 CONFIRMACIONES
    
    1. Toma SOLO la última vela CERRADA
    2. Busca esa vela en el historial (1000 velas)
    3. CONFIRMA 2 VECES la coincidencia
    4. Predice cómo terminará la vela EN MOVIMIENTO
    """
    if len(candles) < 20:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["Datos insuficientes - necesita 20 velas"],
            "votos_buy": 0,
            "votos_sell": 0,
            "patrones_encontrados": 0,
            "pct_acierto": 0,
            "verificacion": False,
            "progreso_vela": 0,
            "velas_analizadas": 0,
            "confirmado": False,
            "confirmaciones": 0,
        }

    # ── 1. SEPARAR VELAS CERRADAS ──────────────────────────────
    ahora = time.time()
    ultima_vela = candles[-1]
    timestamp_vela = ultima_vela["timestamp"]
    tiempo_abierta = ahora - timestamp_vela
    
    if tiempo_abierta < timeframe_seg:
        # La última vela está en movimiento
        velas_cerradas = candles[:-1]
        vela_actual = candles[-1]  # La que está en movimiento
        vela_en_movimiento = True
    else:
        velas_cerradas = candles
        vela_actual = None
        vela_en_movimiento = False
    
    if len(velas_cerradas) < 5:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["No hay suficientes velas cerradas"],
            "votos_buy": 0,
            "votos_sell": 0,
            "patrones_encontrados": 0,
            "pct_acierto": 0,
            "verificacion": False,
            "progreso_vela": 0,
            "velas_analizadas": len(velas_cerradas),
            "confirmado": False,
            "confirmaciones": 0,
        }

    # ── 2. TOMAR LA ÚLTIMA VELA CERRADA ──────────────────────
    ultima_cerrada = velas_cerradas[-1]
    closes = [c["close"] for c in velas_cerradas]
    
    # ── 3. ANALIZAR LA ÚLTIMA VELA CERRADA ──────────────────
    estructura_ultima = analizar_estructura_vela(ultima_cerrada)
    
    # ── 4. BUSCAR EN HISTORIAL CON CONFIRMACIÓN ──────────────
    historial = velas_cerradas[:-1]  # Excluir la última cerrada
    resultados = buscar_vela_con_confirmacion(historial, ultima_cerrada, MAX_VELAS_HISTORIAL)
    analisis = analizar_resultados_vela(resultados)

    # ── 5. INDICADORES ──────────────────────────────────────────
    rsi_val = rsi_rapida(closes, min(14, len(closes)))
    tendencia, fuerza_tendencia = tendencia_rapida(closes, min(20, len(closes)))

    # ── 6. DECISIÓN ──────────────────────────────────────────────
    direccion = "ESPERAR"
    confianza = 0
    razones = []
    
    # ✅ SOLO SI HAY 2 CONFIRMACIONES
    if analisis["confirmado"]:
        if analisis["pct_up"] >= CONFIANZA_MINIMA:
            direccion = "BUY"
            confianza = analisis["confianza"]
            razones.append(f"📊 Vela: {estructura_ultima['tipo']} ({estructura_ultima['color']})")
            razones.append(f"✅ {analisis['confirmaciones']} confirmaciones en historial")
            razones.append(f"📈 {analisis['pct_up']}% de las veces → VERDE")
            razones.append(f"📈 Tipo siguiente: {analisis['tipo_mas_comun']}")
        elif analisis["pct_down"] >= CONFIANZA_MINIMA:
            direccion = "SELL"
            confianza = analisis["confianza"]
            razones.append(f"📊 Vela: {estructura_ultima['tipo']} ({estructura_ultima['color']})")
            razones.append(f"✅ {analisis['confirmaciones']} confirmaciones en historial")
            razones.append(f"📉 {analisis['pct_down']}% de las veces → ROJA")
            razones.append(f"📉 Tipo siguiente: {analisis['tipo_mas_comun']}")
    
    if direccion == "ESPERAR":
        if analisis["confirmado"]:
            razones = ["No hay suficiente confianza en las confirmaciones"]
        else:
            razones = [f"Solo {analisis['confirmaciones']} confirmaciones (necesita {CONFIRMACIONES_REQUERIDAS})"]

    # ── 7. INFORMACIÓN DE LA VELA EN MOVIMIENTO ──────────────
    if vela_en_movimiento and vela_actual:
        estructura_actual = analizar_estructura_vela(vela_actual)
        razones.append(f"⏳ VELA EN MOVIMIENTO: {estructura_actual['tipo']} ({estructura_actual['color']})")
        
        if direccion != "ESPERAR":
            razones.append(f"🎯 PREDICCIÓN: La vela en movimiento terminará {direccion}")
        else:
            razones.append(f"⚠️ Esperando más confirmaciones")

    return {
        "direccion": direccion,
        "confianza": confianza,
        "razones": razones,
        "votos_buy": analisis["up_count"],
        "votos_sell": analisis["down_count"],
        "patrones_encontrados": analisis["total"],
        "pct_acierto": analisis["pct_ganador"],
        "verificacion": analisis["confirmado"],
        "progreso_vela": 0,
        "velas_analizadas": len(velas_cerradas),
        "vela_en_movimiento": vela_en_movimiento,
        "confirmado": analisis["confirmado"],
        "confirmaciones": analisis["confirmaciones"],
        "estructura_ultima": estructura_ultima["tipo"],
        "color_ultima": estructura_ultima["color"],
        "tipo_mas_comun": analisis["tipo_mas_comun"],
        "fuerza_promedio_siguiente": analisis["fuerza_promedio"],
        "indicadores": {
            "precio": round(closes[-1], 6),
            "rsi": round(rsi_val, 1),
            "tendencia": tendencia,
            "tendencia_fuerza": fuerza_tendencia,
            "confirmaciones": analisis["confirmaciones"],
            "confirmado": analisis["confirmado"],
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
    return "vela_unica", detectar_volatilidad(candles)

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
