"""
analysis.py v10.0 — BUSCADOR DE PATRONES REPETITIVOS
- Busca el MISMO patrón en TODO el historial
- Calcula el porcentaje de acierto
- Predice basado en DATOS REALES
"""

def crear_firma(candles, cantidad=5):
    """Crea una firma única de las últimas N velas"""
    if len(candles) < cantidad:
        return None
    
    firma = []
    for i in range(cantidad):
        vela = candles[-(i+1)]
        if vela["close"] > vela["open"]:
            firma.append("V")  # Verde
        else:
            firma.append("R")  # Roja
    
    # También guardar el tamaño de la vela
    tamanos = []
    for i in range(cantidad):
        vela = candles[-(i+1)]
        cuerpo = abs(vela["close"] - vela["open"])
        rango = vela["high"] - vela["low"] if vela["high"] != vela["low"] else 0.00001
        if cuerpo / rango > 0.7:
            tamanos.append("G")  # Grande
        elif cuerpo / rango > 0.3:
            tamanos.append("M")  # Medio
        else:
            tamanos.append("P")  # Pequeño
    
    return "".join(firma) + "|" + "".join(tamanos)

def buscar_patron(candles_historicas, patron_actual, profundidad=500):
    """
    Busca el patrón actual en el historial
    Retorna: resultados de la siguiente vela
    """
    if len(candles_historicas) < profundidad:
        return []
    
    resultados = []
    
    for i in range(len(candles_historicas) - 5):
        bloque = candles_historicas[i:i+5]
        if len(bloque) < 5:
            continue
        
        firma_bloque = crear_firma(bloque, 5)
        if not firma_bloque:
            continue
        
        if firma_bloque == patron_actual:
            # Ver qué pasó después
            if i + 5 < len(candles_historicas):
                siguiente = candles_historicas[i+5]
                resultados.append({
                    "direccion": "UP" if siguiente["close"] > siguiente["open"] else "DOWN",
                    "cambio": (siguiente["close"] - siguiente["open"]) / siguiente["open"] * 100
                })
    
    return resultados

def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    MOTOR v10.0 — BUSCADOR DE PATRONES
    """
    if len(candles) < 50:
        return {
            "direccion": "ESPERAR",
            "confianza": 0,
            "razones": ["Datos insuficientes (necesita 50 velas)"],
            "votos_buy": 0,
            "votos_sell": 0,
        }
    
    # 1. Crear firma del patrón actual
    patron_actual = crear_firma(candles, 5)
    if not patron_actual:
        return {"direccion": "ESPERAR", "confianza": 0}
    
    # 2. Buscar patrón en historial
    resultados = buscar_patron(candles[:-1], patron_actual, 500)
    
    # 3. Analizar resultados
    if resultados:
        up_count = sum(1 for r in resultados if r["direccion"] == "UP")
        down_count = len(resultados) - up_count
        total = len(resultados)
        
        pct_up = (up_count / total) * 100
        pct_down = (down_count / total) * 100
        
        # Cambio promedio
        cambio_promedio = sum(r["cambio"] for r in resultados) / total
        
        # 4. Decisión
        if total >= 5:  # Mínimo 5 repeticiones
            if pct_up >= 70:
                direccion = "BUY"
                confianza = round(pct_up)
                razones = [
                    f"Patrón encontrado {total} veces",
                    f"Subió {up_count} veces ({pct_up}%)",
                    f"Cambio promedio: {cambio_promedio:.2f}%"
                ]
            elif pct_down >= 70:
                direccion = "SELL"
                confianza = round(pct_down)
                razones = [
                    f"Patrón encontrado {total} veces",
                    f"Bajó {down_count} veces ({pct_down}%)",
                    f"Cambio promedio: {cambio_promedio:.2f}%"
                ]
            else:
                direccion = "ESPERAR"
                confianza = 0
                razones = [f"Patrón encontrado {total} veces, pero sin mayoría clara"]
        else:
            direccion = "ESPERAR"
            confianza = 0
            razones = [f"Patrón encontrado solo {total} veces (mínimo 5 necesario)"]
    else:
        direccion = "ESPERAR"
        confianza = 0
        razones = ["Patrón NO encontrado en el historial"]
    
    return {
        "direccion": direccion,
        "confianza": confianza,
        "razones": razones,
        "votos_buy": up_count if resultados else 0,
        "votos_sell": down_count if resultados else 0,
        "score_buy": up_count * 2 if resultados else 0,
        "score_sell": down_count * 2 if resultados else 0,
        "volatilidad": "media",
        "tendencia": "UP" if direccion == "BUY" else "DOWN" if direccion == "SELL" else "LATERAL",
        "patrones_encontrados": len(resultados) if resultados else 0,
        "pct_acierto": confianza if resultados else 0,
        "cambio_promedio": cambio_promedio if resultados else 0,
    }
