def generar_senal(candles, estrategia="auto", timeframe_seg=60):
    """
    CORREGIDO: Usa SOLO velas CERRADAS para el análisis
    """
    if len(candles) < 30:
        return {"direccion": "ESPERAR", "confianza": 0, "razones": ["Datos insuficientes"]}

    # ── 1. SEPARAR VELAS CERRADAS DE LA ACTUAL ──────────────
    # La última vela puede estar en movimiento
    # Usamos SOLO velas CERRADAS (excluyendo la última si está incompleta)
    
    # Verificar si la última vela está completa (cerrada)
    ultima_vela = candles[-1]
    ahora = time.time()
    timestamp_vela = ultima_vela["timestamp"]
    
    # Si la vela es muy reciente (últimos 5 segundos), está en movimiento
    if ahora - timestamp_vela < 5:
        # Excluir la vela actual (en movimiento)
        velas_cerradas = candles[:-1]
        log.info("⚠️ Vela actual en movimiento - excluida del análisis")
    else:
        # La vela ya está cerrada
        velas_cerradas = candles
    
    # ── 2. TOMAR LAS ÚLTIMAS 5 VELAS CERRADAS ──────────────
    if len(velas_cerradas) < 5:
        return {"direccion": "ESPERAR", "confianza": 0, "razones": ["No hay suficientes velas cerradas"]}
    
    # Las últimas 5 velas CERRADAS (TODAS completas)
    ultimas_5_cerradas = velas_cerradas[-5:]
    
    # ── 3. CREAR FIRMA CON SOLO VELAS CERRADAS ──────────────
    patron_actual = crear_firma_velas_detallada(ultimas_5_cerradas, 5)
    
    # ── 4. BUSCAR EN HISTORIAL (también con velas cerradas) ──
    historial_cerradas = velas_cerradas[:-5]  # Excluir las que usamos para el patrón
    resultados = buscar_patron_profundo(historial_cerradas, patron_actual, MAX_VELAS_HISTORIAL)
    
    # ── 5. VERIFICAR LA VELA ACTUAL (en movimiento) ──────────
    # La vela actual (en movimiento) se usa SOLO para verificar
    vela_actual = candles[-1]
    
    # ── 6. PREDECIR LA PRÓXIMA VELA ──────────────────────────
    # La predicción es para la vela DESPUÉS de la actual
    
    return {
        "direccion": direccion,
        "confianza": confianza,
        "razones": razones,
        "velas_analizadas": len(ultimas_5_cerradas),
        "vela_actual_en_movimiento": True,  # Siempre es verdad
        "prediccion_para": "próxima vela (después de la actual)",
        "patron_usado": "últimas 5 velas CERRADAS",
    }
