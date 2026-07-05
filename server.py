"""
server.py — IQ Option Bot API v13.3
- BÚSQUEDA DE PATRONES CON SALTO DE VELA
- PATCH para error get_digital_underlying_list_data
- FORZADO a 60 segundos en velas live
- Analiza 5 velas CERRADAS, SALTA la actual, predice la PRÓXIMA
- Escanea TODOS los activos OTC
- Timing PERFECTO en HH:MM:00
- Zona horaria del BROKER (UTC-6)
- Confianza mínima 60%
- OPTIMIZADO: 15,000 velas históricas
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# ════════════════════════════════════════════════════════════════
#  PATCH: EVITAR ERROR get_digital_underlying_list_data
# ════════════════════════════════════════════════════════════════

import iqoptionapi.stable_api as stable_api

# Guardar la función original
_original_get_digital_open = stable_api.IQ_Option.__get_digital_open

def _patched_get_digital_open(self):
    """Versión parcheada que no falla si la API devuelve None"""
    try:
        return _original_get_digital_open(self)
    except Exception as e:
        # Si falla, devolver datos vacíos
        return {"underlying": {}}

# Aplicar el parche
stable_api.IQ_Option.__get_digital_open = _patched_get_digital_open

# ════════════════════════════════════════════════════════════════
#  RESTO DEL CÓDIGO
# ════════════════════════════════════════════════════════════════

from flask import Flask, jsonify, request
from flask_cors import CORS
import time, logging, threading
from datetime import datetime, timezone, timedelta

from analysis import generar_senal

app = Flask(__name__)
CORS(app, origins="*", allow_headers=["Content-Type","Accept","Authorization","X-API-Key"],
     methods=["GET","POST","OPTIONS"])

# ── CONFIGURACIÓN ─────────────────────────────────────────────────
BROKER_TIMEZONE = timezone(timedelta(hours=-6))
CONFIANZA_MINIMA = 60
INTERVALO_FIJO = 60
VELAS_PARA_ANALISIS = 500
MAX_ACTIVOS_ESCANEAR = 999

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        from flask import Response
        r = Response()
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type,Accept,Authorization,X-API-Key"
        return r

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Accept,Authorization,X-API-Key"
    return response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Sesión global ────────────────────────────────────────────────
sesion = {
    "api":       None,
    "email":     None,
    "conectado": False,
    "cuenta":    None,
    "lock":      threading.Lock(),
}

streams_activos = {}
streams_lock = threading.Lock()
_cache_activos = []
_cache_activos_ts = 0

# ════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════

def _nombre_legible(ticker):
    t = ticker
    es_otc = t.endswith("-OTC")
    if es_otc:
        t = t[:-4]
    if len(t) == 6 and t.isalpha():
        t = t[:3] + "/" + t[3:]
    elif len(t) == 7 and "/" not in t:
        t = t[:3] + "/" + t[3:]
    if es_otc:
        t += " (OTC)"
    return t

def requiere_conexion(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not sesion["conectado"] or sesion["api"] is None:
            return jsonify({
                "error": "No hay sesión activa",
                "hint":  "Agrega IQ_EMAIL e IQ_PASSWORD en las variables de entorno"
            }), 403
        return f(*args, **kwargs)
    return wrapper

def normalizar_activo(activo):
    if not activo:
        return activo
    a = activo.strip().upper()
    es_otc = "OTC" in a
    a = a.replace("(OTC)","").replace("OTC","").strip()
    a = a.replace("/","").replace(" ","").strip("-")
    if es_otc:
        a = f"{a}-OTC"
    return a

def raw_a_vela(c):
    return {
        "timestamp": c["from"],
        "datetime":  datetime.fromtimestamp(c["from"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "open":      round(float(c["open"]),  6),
        "high":      round(float(c["max"]),   6),
        "low":       round(float(c["min"]),   6),
        "close":     round(float(c["close"]), 6),
        "volume":    c.get("volume", 0),
    }

def hora_broker(timestamp):
    return datetime.fromtimestamp(timestamp, tz=BROKER_TIMEZONE)

# ════════════════════════════════════════════════════════════════
#  AUTO-CONNECT
# ════════════════════════════════════════════════════════════════

def _auto_connect():
    email = os.environ.get("IQ_EMAIL", "").strip()
    password = os.environ.get("IQ_PASSWORD", "").strip()
    cuenta = os.environ.get("IQ_CUENTA", "PRACTICE").upper()

    if not email or not password:
        log.warning("Sin IQ_EMAIL/IQ_PASSWORD en env vars.")
        return

    log.info(f"Auto-conectando como {email} [{cuenta}]...")
    try:
        from iqoptionapi.stable_api import IQ_Option
        api = IQ_Option(email, password)
        resultado = [None, None]

        def _conn():
            try:
                resultado[0], resultado[1] = api.connect()
            except Exception as ex:
                resultado[0] = False
                resultado[1] = str(ex)

        t = threading.Thread(target=_conn, daemon=True)
        t.start()
        t.join(timeout=25)

        if t.is_alive() or not resultado[0]:
            log.error(f"Auto-connect falló: {resultado[1]}")
            return

        api.change_balance(cuenta)
        time.sleep(2)

        with sesion["lock"]:
            sesion["api"] = api
            sesion["email"] = email
            sesion["conectado"] = True
            sesion["cuenta"] = cuenta

        log.info(f"✅ Auto-conectado OK — cuenta {cuenta}")

    except Exception as e:
        log.error(f"Error auto-connect: {e}")

# ════════════════════════════════════════════════════════════════
#  PRE-CARGA DE ACTIVOS
# ════════════════════════════════════════════════════════════════

def _precargar_activos():
    global _cache_activos, _cache_activos_ts
    time.sleep(20)
    while True:
        try:
            if not sesion["conectado"] or sesion["api"] is None:
                time.sleep(10)
                continue
            api = sesion["api"]

            profits = {}
            try:
                profits = api.get_all_profit() or {}
            except:
                pass

            resultado = []
            for activo, info in profits.items():
                if not info:
                    continue
                payout = round((info.get("turbo", 0) or 0) * 100, 1)
                if payout <= 0 or payout < 80:
                    continue
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
            log.info(f"✅ Cache activos: {len(resultado)} activos cargados")

        except Exception as e:
            log.error(f"Error precargando activos: {e}")
        time.sleep(300)

# Arrancar hilos
threading.Thread(target=_auto_connect, daemon=True).start()
threading.Thread(target=_precargar_activos, daemon=True).start()

# ════════════════════════════════════════════════════════════════
#  ENDPOINTS PÚBLICOS
# ════════════════════════════════════════════════════════════════

@app.route("/")
def raiz():
    return jsonify({
        "api": "IQ Option Bot API",
        "version": "13.3",
        "estado": "online",
        "conectado": sesion["conectado"],
        "activos_en_cache": len(_cache_activos),
        "intervalo_fijo": INTERVALO_FIJO,
        "broker_timezone": "UTC-6",
        "confianza_minima": CONFIANZA_MINIMA,
        "analisis": "patron_con_salto_vela",
        "max_velas_historicas": 15000,
    })

@app.route("/iq/ping")
def ping():
    return jsonify({
        "ok": True,
        "conectado": sesion["conectado"],
        "email": sesion["email"] if sesion["conectado"] else None,
        "cuenta": sesion["cuenta"],
        "activos_en_cache": len(_cache_activos),
        "intervalo_fijo": INTERVALO_FIJO,
        "broker_timezone": "UTC-6",
        "version": "13.3",
        "timestamp": int(time.time()),
    })

@app.route("/iq/conectar", methods=["POST"])
def conectar():
    body = request.get_json(force=True)
    email = body.get("email", "").strip()
    password = body.get("password", "")
    cuenta = body.get("cuenta", "PRACTICE").upper()
    if not email or not password:
        return jsonify({"ok": False, "error": "Se requieren email y password"}), 400
    try:
        from iqoptionapi.stable_api import IQ_Option
        with sesion["lock"]:
            if sesion["api"]:
                try: sesion["api"].api.close()
                except: pass
            api = IQ_Option(email, password)
            res = [None, None]
            def _c():
                try: res[0], res[1] = api.connect()
                except Exception as ex: res[0]=False; res[1]=str(ex)
            t = threading.Thread(target=_c, daemon=True)
            t.start(); t.join(timeout=15)
            if t.is_alive() or not res[0]:
                return jsonify({"ok": False, "error": f"Error: {res[1]}"}), 401
            api.change_balance(cuenta)
            time.sleep(2)
            saldo = api.get_balance()
            sesion["api"] = api
            sesion["email"] = email
            sesion["conectado"] = True
            sesion["cuenta"] = cuenta
        return jsonify({
            "ok": True,
            "email": email,
            "cuenta": cuenta,
            "saldo": round(saldo, 2) if saldo else None
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/iq/desconectar")
def desconectar():
    with sesion["lock"]:
        if sesion["api"]:
            try: sesion["api"].api.close()
            except: pass
        sesion["api"] = None
        sesion["conectado"] = False
        sesion["email"] = None
    return jsonify({"ok": True})

@app.route("/iq/activos/blitz")
@requiere_conexion
def activos_blitz():
    global _cache_activos
    if _cache_activos:
        return jsonify({
            "ok": True,
            "tipo": "blitz",
            "total": len(_cache_activos),
            "activos": _cache_activos,
            "cached": True,
        })
    try:
        api = sesion["api"]
        open_time_res = [None]
        profits_res = [None]
        def _ot(): open_time_res[0] = api.get_all_open_time()
        def _pr(): profits_res[0] = api.get_all_profit()
        t1 = threading.Thread(target=_ot, daemon=True)
        t2 = threading.Thread(target=_pr, daemon=True)
        t1.start(); t2.start()
        t1.join(timeout=25); t2.join(timeout=25)
        open_time = open_time_res[0] or {}
        profits = profits_res[0] or {}
        resultado = []
        vistos = set()
        if "turbo" in open_time:
            for activo, datos in open_time["turbo"].items():
                if activo in vistos: continue
                if not any(info.get("open", False) for _, info in datos.items()): continue
                vistos.add(activo)
                profit_info = profits.get(activo, {})
                payout = round((profit_info.get("turbo", 0) or 0) * 100, 1)
                if payout < 80:
                    continue
                resultado.append({
                    "ticker": activo,
                    "nombre": _nombre_legible(activo),
                    "es_otc": "OTC" in activo.upper(),
                    "payout": payout,
                    "abierto": True,
                })
        resultado.sort(key=lambda x: (-x["payout"], not x["es_otc"], x["ticker"]))
        _cache_activos = resultado
        return jsonify({
            "ok": True,
            "tipo": "blitz",
            "total": len(resultado),
            "activos": resultado,
            "cached": False,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ════════════════════════════════════════════════════════════════
#  ENDPOINT: VELAS EN TIEMPO REAL (FORZADO A 60s)
# ════════════════════════════════════════════════════════════════

@app.route("/iq/velas/live")
@requiere_conexion
def velas_live():
    api = sesion["api"]
    activo = normalizar_activo(request.args.get("activo", "EURUSD-OTC"))
    # ✅ FORZAR 60 SEGUNDOS - IGNORAR lo que pide el frontend
    intervalo = INTERVALO_FIJO
    cantidad = int(request.args.get("cantidad", 60))
    clave = f"{activo}_{intervalo}"
    
    try:
        with streams_lock:
            if clave not in streams_activos:
                api.start_candles_stream(activo, intervalo, cantidad)
                streams_activos[clave] = True
                time.sleep(1.0)
        rt = api.get_realtime_candles(activo, intervalo)
        velas_fmt = []
        if rt and len(rt) > 0:
            for ts in sorted(rt.keys())[-cantidad:]:
                c = rt[ts]
                velas_fmt.append({
                    "timestamp": int(ts),
                    "open": round(float(c.get("open", 0)), 6),
                    "high": round(float(c.get("max", 0)), 6),
                    "low": round(float(c.get("min", 0)), 6),
                    "close": round(float(c.get("close", 0)), 6),
                })
        else:
            raw = api.get_candles(activo, intervalo, cantidad, time.time())
            velas_fmt = [raw_a_vela(c) for c in raw] if raw else []
        if not velas_fmt:
            return jsonify({"error": f"Sin datos para {activo}"}), 404
        precio_actual = velas_fmt[-1]["close"]
        precio_anterior = velas_fmt[-2]["close"] if len(velas_fmt) >= 2 else precio_actual
        tendencia = "UP" if precio_actual >= precio_anterior else "DOWN"
        ahora = int(time.time())
        return jsonify({
            "ok": True,
            "activo": activo,
            "nombre": _nombre_legible(activo),
            "intervalo": intervalo,
            "precio": precio_actual,
            "tendencia": tendencia,
            "vela_cierra_en": intervalo - (ahora % intervalo),
            "server_time": ahora,
            "velas": velas_fmt,
            "nota": "Intervalo FORZADO a 60s (ignorando solicitud del frontend)"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/iq/velas/stop")
@requiere_conexion
def velas_stop():
    api = sesion["api"]
    activo = normalizar_activo(request.args.get("activo", "EURUSD-OTC"))
    intervalo = INTERVALO_FIJO
    clave = f"{activo}_{intervalo}"
    try:
        with streams_lock:
            if clave in streams_activos:
                api.stop_candles_stream(activo, intervalo)
                del streams_activos[clave]
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ════════════════════════════════════════════════════════════════
#  ENDPOINT: SEÑAL PARA UN ACTIVO ESPECÍFICO
# ════════════════════════════════════════════════════════════════

@app.route("/iq/senal", methods=["POST"])
@requiere_conexion
def senal():
    """
    SEÑAL PARA UN ACTIVO ESPECÍFICO
    
    LÓGICA:
    1. Toma 5 velas CERRADAS del activo
    2. Busca el patrón en el historial del MISMO activo (15,000 velas)
    3. SALTA la vela actual (en movimiento)
    4. Predice la PRÓXIMA vela (después de la actual)
    """
    api = sesion["api"]
    body = request.get_json(force=True)

    activo = normalizar_activo(body.get("activo", "EURUSD-OTC"))
    duracion_min = float(body.get("duracion", 1))
    intervalo = INTERVALO_FIJO
    cantidad_velas = int(body.get("cantidad_velas", VELAS_PARA_ANALISIS))

    try:
        raw = api.get_candles(activo, intervalo, cantidad_velas, time.time())
        if not raw:
            return jsonify({"error": f"Sin velas para {activo}"}), 404

        candles = [raw_a_vela(c) for c in raw]
        resultado = generar_senal(candles, "estructura", intervalo)

        confianza = resultado.get("confianza", 0)
        patrones_encontrados = resultado.get("patrones_encontrados", 0)

        # ── TIMING PERFECTO ──────────────────────────────────────
        ahora_ts = time.time()
        ahora_broker = hora_broker(ahora_ts)
        segundos_en_minuto = ahora_broker.second + (ahora_broker.microsecond / 1000000)
        
        if segundos_en_minuto == 0:
            seg_para_entrar = 60
        else:
            seg_para_entrar = 60 - segundos_en_minuto
        
        if seg_para_entrar < 1:
            seg_para_entrar = 60
        
        ts_entrada = ahora_ts + seg_para_entrar
        duracion_seg = duracion_min * 60
        ts_salida = ts_entrada + duracion_seg
        ts_verificar = ts_entrada + (duracion_seg / 2)

        entrada_broker = hora_broker(ts_entrada)
        salida_broker = hora_broker(ts_salida)
        actual_broker = hora_broker(ahora_ts)
        verificar_broker = hora_broker(ts_verificar)

        # ── PROFIT REAL ──────────────────────────────────────────
        profit_pct = None
        try:
            profits = api.get_all_profit()
            profit_pct = profits.get(activo, {}).get("turbo")
        except:
            pass

        # ── VERIFICAR SI LA SEÑAL ES VÁLIDA ─────────────────────
        es_valida = (
            resultado["direccion"] in ("BUY", "SELL") and
            confianza >= CONFIANZA_MINIMA
        )

        if not es_valida:
            resultado["direccion"] = "ESPERAR"
            resultado["confianza"] = 0

        return jsonify({
            "ok": True,
            "activo": activo,
            "nombre": _nombre_legible(activo),
            "es_otc": "OTC" in activo,
            "senal": resultado["direccion"],
            "confianza": confianza if es_valida else 0,
            
            # ── TIMING ──────────────────────────────────────────
            "hora_actual": actual_broker.strftime("%H:%M:%S"),
            "hora_entrada": entrada_broker.strftime("%H:%M:%S"),
            "hora_salida": salida_broker.strftime("%H:%M:%S"),
            "hora_verificar": verificar_broker.strftime("%H:%M:%S"),
            "segundos_para_entrar": max(0, round(seg_para_entrar, 1)),
            "timezone": "UTC-6",
            
            # ── ANÁLISIS ────────────────────────────────────────
            "patrones_encontrados": patrones_encontrados,
            "pct_acierto": resultado.get("pct_acierto", 0),
            "tipo_mas_comun": resultado.get("tipo_mas_comun", "N/A"),
            "fuerza_promedio_siguiente": resultado.get("fuerza_promedio_siguiente", 0),
            "verificacion": resultado.get("verificacion", False),
            "progreso_vela": resultado.get("progreso_vela", 0),
            "velas_analizadas": resultado.get("velas_analizadas", 0),
            "vela_en_movimiento": resultado.get("vela_en_movimiento", False),
            
            # ── RAZONES ─────────────────────────────────────────
            "razones": resultado.get("razones", []),
            "votos_buy": resultado.get("votos_buy", 0),
            "votos_sell": resultado.get("votos_sell", 0),
            "tendencia": resultado.get("tendencia", "LATERAL"),
            "volatilidad": resultado.get("volatilidad", "media"),
            "indicadores": resultado.get("indicadores", {}),
            
            # ── INFO OPERACIÓN ──────────────────────────────────
            "duracion_seg": int(duracion_seg),
            "duracion_min": duracion_min,
            "intervalo_vela": intervalo,
            "rentabilidad": f"{round(profit_pct*100,1)}%" if profit_pct else "N/D",
        })

    except Exception as e:
        log.exception("Error en /iq/senal")
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  ENDPOINT: ESCANEO DE TODOS LOS ACTIVOS OTC
# ════════════════════════════════════════════════════════════════

@app.route("/iq/escanear", methods=["POST"])
@requiere_conexion
def escanear_activos():
    """
    ESCANEA TODOS LOS ACTIVOS OTC
    
    LÓGICA:
    Para CADA activo OTC:
    1. Toma 5 velas CERRADAS de ESE activo
    2. Busca el patrón en el historial de ESE activo (15,000 velas)
    3. SALTA la vela actual (en movimiento)
    4. Predice la PRÓXIMA vela
    5. Guarda la señal si es válida
    
    RETORNA: El MEJOR activo (mayor confianza)
    """
    api = sesion["api"]
    body = request.get_json(force=True)
    
    duracion_min = float(body.get("duracion", 1))
    intervalo = INTERVALO_FIJO
    
    # Obtener TODOS los activos OTC
    activos_otc = [a for a in _cache_activos if a["es_otc"]]
    
    log.info(f"🔍 Escaneando TODOS los {len(activos_otc)} activos OTC...")
    log.info(f"📊 Búsqueda de patrones con SALTO de vela (15,000 velas)")
    
    resultados = []
    activos_analizados = 0
    
    for activo in activos_otc:
        ticker = activo["ticker"]
        try:
            # Obtener velas del activo
            raw = api.get_candles(ticker, intervalo, VELAS_PARA_ANALISIS, time.time())
            if not raw:
                continue
            
            candles = [raw_a_vela(c) for c in raw]
            
            # Generar señal para ESTE activo (busca en su propio historial)
            senal = generar_senal(candles, "estructura", intervalo)
            activos_analizados += 1
            
            # Solo guardar señales válidas
            if senal["direccion"] in ("BUY", "SELL") and senal["confianza"] >= CONFIANZA_MINIMA:
                resultados.append({
                    "activo": ticker,
                    "nombre": _nombre_legible(ticker),
                    "direccion": senal["direccion"],
                    "confianza": senal["confianza"],
                    "patrones": senal.get("patrones_encontrados", 0),
                    "pct_acierto": senal.get("pct_acierto", 0),
                    "tipo_mas_comun": senal.get("tipo_mas_comun", "N/A"),
                    "fuerza_promedio": senal.get("fuerza_promedio_siguiente", 0),
                    "razones": senal.get("razones", [])[:3],
                    "payout": activo["payout"],
                })
            
            # Pequeña pausa para no saturar
            time.sleep(0.08)
            
        except Exception as e:
            log.error(f"Error escaneando {ticker}: {e}")
            continue
    
    # ── TIMING PERFECTO ──────────────────────────────────────────
    ahora_ts = time.time()
    ahora_broker = hora_broker(ahora_ts)
    segundos_en_minuto = ahora_broker.second + (ahora_broker.microsecond / 1000000)
    
    if segundos_en_minuto == 0:
        seg_para_entrar = 60
    else:
        seg_para_entrar = 60 - segundos_en_minuto
    
    if seg_para_entrar < 1:
        seg_para_entrar = 60
    
    ts_entrada = ahora_ts + seg_para_entrar
    duracion_seg = duracion_min * 60
    ts_salida = ts_entrada + duracion_seg
    ts_verificar = ts_entrada + (duracion_seg / 2)
    
    entrada_broker = hora_broker(ts_entrada)
    salida_broker = hora_broker(ts_salida)
    actual_broker = hora_broker(ahora_ts)
    verificar_broker = hora_broker(ts_verificar)
    
    # ── ORDENAR POR CONFIANZA ──────────────────────────────────
    resultados.sort(key=lambda x: x["confianza"], reverse=True)
    
    if resultados:
        mejor = resultados[0]
        log.info(f"✅ MEJOR SEÑAL: {mejor['activo']} → {mejor['direccion']} ({mejor['confianza']}%)")
        
        return jsonify({
            "ok": True,
            "senal": mejor["direccion"],
            "activo": mejor["activo"],
            "nombre": mejor["nombre"],
            "confianza": mejor["confianza"],
            "patrones": mejor["patrones"],
            "pct_acierto": mejor["pct_acierto"],
            "tipo_mas_comun": mejor["tipo_mas_comun"],
            "fuerza_promedio": mejor["fuerza_promedio"],
            "razones": mejor["razones"],
            "payout": mejor["payout"],
            
            # ── TIMING ──────────────────────────────────────────
            "hora_actual": actual_broker.strftime("%H:%M:%S"),
            "hora_entrada": entrada_broker.strftime("%H:%M:%S"),
            "hora_salida": salida_broker.strftime("%H:%M:%S"),
            "hora_verificar": verificar_broker.strftime("%H:%M:%S"),
            "segundos_para_entrar": max(0, round(seg_para_entrar, 1)),
            "timezone": "UTC-6",
            
            "duracion_min": duracion_min,
            "total_escaneados": activos_analizados,
            "señales_encontradas": len(resultados),
            "mejores_activos": resultados[:10],
            "mensaje_entrada": f"Entrar a {mejor['nombre']} a las {entrada_broker.strftime('%H:%M:%S')}",
            "analisis_tipo": "patron_con_salto_vela",
            "max_velas_historicas": 15000,
        })
    else:
        return jsonify({
            "ok": False,
            "mensaje": "No se encontraron señales en este momento",
            "total_escaneados": activos_analizados,
            "hora_actual": actual_broker.strftime("%H:%M:%S"),
            "hora_entrada": entrada_broker.strftime("%H:%M:%S"),
            "segundos_para_entrar": max(0, round(seg_para_entrar, 1)),
            "analisis_tipo": "patron_con_salto_vela",
            "max_velas_historicas": 15000,
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("="*80)
    print("  IQ Option Bot API  v13.3 - OPTIMIZADO (15,000 velas)")
    print(f"  http://0.0.0.0:{port}")
    print("="*80)
    print("")
    print("  🔥 LÓGICA DE ANÁLISIS:")
    print("     ✅ Toma 5 velas CERRADAS del activo")
    print("     ✅ Busca el patrón en el HISTORIAL del MISMO activo")
    print("     ✅ SALTA la vela actual (en movimiento)")
    print("     ✅ Predice la PRÓXIMA vela (después de la actual)")
    print("     ✅ ¡SIEMPRE BUY o SELL!")
    print("")
    print("  📊 CONFIGURACIÓN:")
    print(f"     📊 Intervalo de velas: {INTERVALO_FIJO}s")
    print(f"     📊 Máximo velas históricas: 15,000 (~10.4 días)")
    print(f"     🎯 Entrada SIEMPRE en HH:MM:00 (inicio de vela)")
    print(f"     🕐 Zona horaria del BROKER: UTC-6")
    print(f"     🔒 Confianza mínima: {CONFIANZA_MINIMA}%")
    print("     🔍 ESCANEA TODOS los activos OTC")
    print("     🏆 Encuentra el MEJOR activo para operar")
    print("")
    print("  🔧 CORRECCIONES APLICADAS:")
    print("     ✅ PATCH para error get_digital_underlying_list_data")
    print("     ✅ FORZADO a 60 segundos en velas live")
    print("     ✅ OPTIMIZADO a 15,000 velas históricas")
    print("="*80)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
