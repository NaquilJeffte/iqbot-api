# Cache de activos para no llamar IQ Option cada vez
_cache_activos = []
_cache_activos_ts = 0

def _precargar_activos():
    """Pre-carga activos en background al arrancar"""
    global _cache_activos, _cache_activos_ts
    time.sleep(15)  # esperar que IQ Option conecte
    while True:
        try:
            if sesion["conectado"] and sesion["api"]:
                api = sesion["api"]
                open_time = api.get_all_open_time()
                profits = api.get_all_profit()
                resultado = []
                vistos = set()
                if "turbo" in open_time:
                    for activo, datos in open_time["turbo"].items():
                        if activo in vistos: continue
                        abierto = any(info.get("open", False) for _, info in datos.items())
                        if not abierto: continue
                        vistos.add(activo)
                        profit_info = profits.get(activo, {})
                        payout = round((profit_info.get("turbo", 0) or 0) * 100, 1)
                        resultado.append({
                            "ticker": activo,
                            "nombre": _nombre_legible(activo),
                            "es_otc": "OTC" in activo.upper(),
                            "payout": payout,
                            "abierto": True,
                        })
                resultado.sort(key=lambda x: (-x["payout"], not x["es_otc"], x["ticker"]))
                _cache_activos = resultado
                _cache_activos_ts = time.time()
                log.info(f"✅ Cache activos: {len(resultado)} activos")
        except Exception as e:
            log.error(f"Error precargando activos: {e}")
        time.sleep(300)  # refrescar cada 5 minutos

threading.Thread(target=_precargar_activos, daemon=True).start()
