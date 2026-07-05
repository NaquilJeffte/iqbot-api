"""
server.py — IQ Option Bot API v15.0
- PREDICCIÓN CON 1 VELA + 2 CONFIRMACIONES
- Analiza SOLO la última vela CERRADA
- Busca esa vela en el historial (1000 velas)
- CONFIRMA 2 VECES la coincidencia
- Predice cómo terminará la vela EN MOVIMIENTO
- 10 ACTIVOS OBLIGATORIOS SIEMPRE VISIBLES
- CORRECCIÓN DE TICKERS ALTERNATIVOS
- PATCH PARA ERROR get_digital_underlying_list_data
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# ════════════════════════════════════════════════════════════════
#  PATCH: EVITAR ERROR get_digital_underlying_list_data
# ════════════════════════════════════════════════════════════════

import iqoptionapi.stable_api as stable_api

_original_get_digital_open = stable_api.IQ_Option.__get_digital_open

def _patched_get_digital_open(self):
    try:
        return _original_get_digital_open(self)
    except Exception:
        return {"underlying": {}}

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
VELAS_PARA_ANALISIS = 1000  # ✅ 1000 velas para buscar confirmaciones
MAX_ACTIVOS_ESCANEAR = 999
CONFIRMACIONES_REQUERIDAS = 2  # ✅ REQUIERE 2 CONFIRMACIONES

# ── 10 ACTIVOS OBLIGATORIOS ────────────────────────────────────
ACTIVOS_OBLIGATORIOS = [
    {"ticker": "EURUSD-OTC", "nombre": "EUR/USD (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "GBPUSD-OTC", "nombre": "GBP/USD (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "EURGBP-OTC", "nombre": "EUR/GBP (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "AUDUSD-OTC", "nombre": "AUD/USD (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "USDJPY-OTC", "nombre": "USD/JPY (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "USDCHF-OTC", "nombre": "USD/CHF (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "XAUUSD-OTC", "nombre": "XAU/USD (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "BTCUSD-OTC", "nombre": "BTC/USD (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "ETHUSD-OTC", "nombre": "ETH/USD (OTC)", "payout": 85, "estrella": "⭐"},
    {"ticker": "EURJPY-OTC", "nombre": "EUR/JPY (OTC)", "payout": 85, "estrella": "⭐"},
]

# ── MAPEO DE TICKERS ALTERNATIVOS ──────────────────────────────
TICKER_ALTERNATIVOS = {
    "EURUSD-OTC": ["EURUSD-OTC", "EURUSD", "EUR-USD"],
    "GBPUSD-OTC": ["GBPUSD-OTC", "GBPUSD", "GBP-USD"],
    "EURGBP-OTC": ["EURGBP-OTC", "EURGBP", "EUR-GBP"],
    "AUDUSD-OTC": ["AUDUSD-OTC", "AUDUSD", "AUD-USD"],
    "USDJPY-OTC": ["USDJPY-OTC", "USDJPY", "USD-JPY"],
    "USDCHF-OTC": ["USDCHF-OTC", "USDCHF", "USD-CHF"],
    "XAUUSD-OTC": ["XAUUSD-OTC", "XAUUSD", "XAU-USD", "GOLD-OTC", "GOLD"],
    "BTCUSD-OTC": ["BTCUSD-OTC", "BTCUSD", "BTC-USD", "BITCOIN-OTC"],
    "ETHUSD-OTC": ["ETHUSD-OTC", "ETHUSD", "ETH-USD", "ETHEREUM-OTC"],
    "EURJPY-OTC": ["EURJPY-OTC", "EURJPY", "EUR-JPY"],
}

# ── MAPEO DE DURACIONES ─────────────────────────────────────────
DURACIONES = [
    {"label": "30s", "valor": 0.5},
    {"label": "45s", "valor": 0.75},
    {"label": "1m", "valor": 1},
    {"label": "2m", "valor": 2},
    {"label": "3m", "valor": 3},
    {"label": "5m", "valor": 5},
]

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
    "api": None,
    "email": None,
    "conectado": False,
    "cuenta": None,
    "lock": threading.Lock(),
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
                "hint": "Agrega IQ_EMAIL e IQ_PASSWORD en las variables de entorno"
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
        "datetime": datetime.fromtimestamp(c["from"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "open": round(float(c["open"]), 6),
        "high": round(float(c["max"]), 6),
        "low": round(float(c["min"]), 6),
        "close": round(float(c["close"]), 6),
        "volume": c.get("volume", 0),
    }

def hora_broker(timestamp):
    return datetime.fromtimestamp(timestamp, tz=BROKER_TIMEZONE)

# ════════════════════════════════════════════════════════════════
#  FUNCIÓN PARA OBTENER VELAS CON FALLBACK DE TICKERS
# ════════════════════════════════════════════════════════════════

def obtener_velas_con_fallback(api, ticker, intervalo, cantidad):
    """Intenta obtener velas con el ticker principal, si falla, prueba con alternativos"""
    tickers_a_probar = TICKER_ALTERNATIVOS.get(ticker, [ticker])
    
    for t in tickers_a_probar:
        try:
            raw = api.get_candles(t, intervalo, cantidad, time.time())
            if raw and len(raw) > 0:
                log.info(f"✅ Velas obtenidas para {ticker} usando: {t}")
                return raw
        except Exception as e:
            continue
    
    log.warning(f"❌ No se pudieron obtener velas para {ticker}")
    return None

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
            # Primero agregar los 10 activos obligatorios
            for activo in ACTIVOS_OBLIGATORIOS:
                resultado.append({
                    "ticker": activo["ticker"],
                    "nombre": activo["nombre"],
                    "es_otc": True,
                    "payout": activo["payout"],
                    "abierto": True,
                    "obligatorio": True,
                    "estrella": activo["estrella"],
                })

            # Luego agregar el resto
            for activo, info in profits.items():
                if not info:
                    continue
                if any(a["ticker"] == activo for a in ACTIVOS_OBLIGATORIOS):
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
                    "obligatorio": False,
                    "estrella": "",
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
        "version": "15.0",
        "estado": "online",
        "conectado": sesion["conectado"],
        "activos_en_cache": len(_cache_activos),
        "intervalo_fijo": INTERVALO_FIJO,
        "broker_timezone": "UTC-6",
        "confianza_minima": CONFIANZA_MINIMA,
        "confirmaciones_requeridas": CONFIRMACIONES_REQUERIDAS,
        "analisis": "1_vela_2_confirmaciones",
        "max_velas_historicas": VELAS_PARA_ANALISIS,
        "activos_obligatorios": len(ACTIVOS_OBLIGATORIOS),
        "duraciones": DURACIONES,
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
        "version": "15.0",
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
            "activos_obligatorios": len(ACTIVOS_OBLIGATORIOS),
        })
    try:
        api = sesion["api"]
        profits = api.get_all_profit() or {}
        resultado = []
        for activo in ACTIVOS_OBLIGATORIOS:
            resultado.append({
                "ticker": activo["ticker"],
                "nombre": activo["nombre"],
                "es_otc": True,
                "payout": activo["payout"],
                "abierto": True,
                "obligatorio": True,
                "estrella": activo["estrella"],
            })
        for activo, info in profits.items():
            if any(a["ticker"] == activo for a in ACTIVOS_OBLIGATORIOS):
                continue
            payout = round((info.get("turbo", 0) or 0) * 100, 1)
            if payout < 80:
                continue
            resultado.append({
                "ticker": activo,
                "nombre": _nombre_legible(activo),
                "es_otc": "OTC" in activo.upper(),
                "payout": payout,
                "abierto": True,
                "obligatorio": False,
                "estrella": "",
            })
        resultado.sort(key=lambda x: (-x["payout"], not x["es_otc"], x["ticker"]))
        _cache_activos = resultado
        return jsonify({
            "ok": True,
            "tipo": "blitz",
            "total": len(resultado),
            "activos": resultado,
            "cached": False,
            "activos_obligatorios": len(ACTIVOS_OBLIGATORIOS),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ════════════════════════════════════════════════════════════════
#  ENDPOINT: VELAS EN TIEMPO REAL
# ════════════════════════════════════════════════════════════════

@app.route("/iq/velas/live")
@requiere_conexion
def velas_live():
    api = sesion["api"]
    activo = normalizar_activo(request.args.get("activo", "EURUSD-OTC"))
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
#  ENDPOINT: SEÑAL PARA UN ACTIVO ESPECÍFICO (1 VELA + 2 CONFIRMACIONES)
# ════════════════════════════════════════════════════════════════

@app.route("/iq/senal", methods=["POST"])
@requiere_conexion
def senal():
    """Señal para un activo específico - 1 vela + 2 confirmaciones"""
    api = sesion["api"]
    body = request.get_json(force=True)

    activo = normalizar_activo(body.get("activo", "EURUSD-OTC"))
    duracion_min = float(body.get("duracion", 1))
    intervalo = INTERVALO_FIJO
    cantidad_velas = int(body.get("cantidad_velas", VELAS_PARA_ANALISIS))

    try:
        raw = obtener_velas_con_fallback(api, activo, intervalo, cantidad_velas)
        if not raw:
            return jsonify({"error": f"Sin velas para {activo}"}), 404

        candles = [raw_a_vela(c) for c in raw]
        resultado = generar_senal(candles, "1_vela", intervalo)

        confianza = resultado.get("confianza", 0)
        confirmado = resultado.get("confirmado", False)
        confirmaciones = resultado.get("confirmaciones", 0)

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

        # ── VALIDAR SEÑAL ──────────────────────────────────────
        es_valida = (
            resultado["direccion"] in ("BUY", "SELL") and
            confianza >= CONFIANZA_MINIMA and
            confirmado  # ✅ REQUIERE 2 CONFIRMACIONES
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
            "confirmado": confirmado,
            "confirmaciones": confirmaciones,
            "confirmaciones_requeridas": CONFIRMACIONES_REQUERIDAS,
            
            "hora_actual": actual_broker.strftime("%H:%M:%S"),
            "hora_entrada": entrada_broker.strftime("%H:%M:%S"),
            "hora_salida": salida_broker.strftime("%H:%M:%S"),
            "hora_verificar": verificar_broker.strftime("%H:%M:%S"),
            "segundos_para_entrar": max(0, round(seg_para_entrar, 1)),
            "timezone": "UTC-6",
            
            "razones": resultado.get("razones", []),
            "votos_buy": resultado.get("votos_buy", 0),
            "votos_sell": resultado.get("votos_sell", 0),
            "tendencia": resultado.get("tendencia", "LATERAL"),
            "volatilidad": resultado.get("volatilidad", "media"),
            "indicadores": resultado.get("indicadores", {}),
            "estructura_ultima": resultado.get("estructura_ultima", "N/A"),
            "color_ultima": resultado.get("color_ultima", "N/A"),
            "tipo_mas_comun": resultado.get("tipo_mas_comun", "N/A"),
            "fuerza_promedio_siguiente": resultado.get("fuerza_promedio_siguiente", 0),
            
            "duracion_seg": int(duracion_seg),
            "duracion_min": duracion_min,
            "intervalo_vela": intervalo,
            "rentabilidad": f"{round(profit_pct*100,1)}%" if profit_pct else "N/D",
        })

    except Exception as e:
        log.exception("Error en /iq/senal")
        return jsonify({"error": str(e)}), 500

# ════════════════════════════════════════════════════════════════
#  ENDPOINT: ESCANEO AUTOMÁTICO DE TODOS LOS ACTIVOS
# ════════════════════════════════════════════════════════════════

@app.route("/iq/escanear", methods=["POST"])
@requiere_conexion
def escanear_activos():
    """
    ESCANEA TODOS LOS ACTIVOS CON 1 VELA + 2 CONFIRMACIONES
    """
    api = sesion["api"]
    body = request.get_json(force=True)
    
    duracion_min = float(body.get("duracion", 1))
    intervalo = INTERVALO_FIJO
    
    activos = _cache_activos if _cache_activos else []
    
    log.info(f"🔍 Escaneando {len(activos)} activos con 1 vela + 2 confirmaciones...")
    
    resultados = []
    activos_analizados = 0
    
    for activo in activos:
        ticker = activo["ticker"]
        try:
            raw = obtener_velas_con_fallback(api, ticker, intervalo, VELAS_PARA_ANALISIS)
            if not raw:
                continue
            
            candles = [raw_a_vela(c) for c in raw]
            senal = generar_senal(candles, "1_vela", intervalo)
            activos_analizados += 1
            
            if senal["direccion"] in ("BUY", "SELL") and senal["confianza"] >= CONFIANZA_MINIMA and senal.get("confirmado", False):
                resultados.append({
                    "activo": ticker,
                    "nombre": _nombre_legible(ticker),
                    "direccion": senal["direccion"],
                    "confianza": senal["confianza"],
                    "confirmaciones": senal.get("confirmaciones", 0),
                    "estructura": senal.get("estructura_ultima", "N/A"),
                    "tipo_mas_comun": senal.get("tipo_mas_comun", "N/A"),
                    "razones": senal.get("razones", [])[:3],
                    "payout": activo["payout"],
                    "es_obligatorio": activo.get("obligatorio", False),
                    "estrella": activo.get("estrella", ""),
                })
            
            time.sleep(0.05)
            
        except Exception as e:
            continue
    
    resultados.sort(key=lambda x: (x["es_obligatorio"] is False, -x["confianza"]))
    
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
    entrada_broker = hora_broker(ts_entrada)
    actual_broker = hora_broker(ahora_ts)
    
    if resultados:
        mejor = resultados[0]
        log.info(f"✅ MEJOR SEÑAL: {mejor['activo']} → {mejor['direccion']} ({mejor['confianza']}%) - {mejor['estructura']}")
        
        return jsonify({
            "ok": True,
            "senal": mejor["direccion"],
            "activo": mejor["activo"],
            "nombre": mejor["nombre"],
            "confianza": mejor["confianza"],
            "confirmaciones": mejor["confirmaciones"],
            "estructura": mejor["estructura"],
            "tipo_mas_comun": mejor["tipo_mas_comun"],
            "razones": mejor["razones"],
            "payout": mejor["payout"],
            "es_obligatorio": mejor.get("es_obligatorio", False),
            "estrella": mejor.get("estrella", ""),
            "confirmaciones_requeridas": CONFIRMACIONES_REQUERIDAS,
            
            "hora_actual": actual_broker.strftime("%H:%M:%S"),
            "hora_entrada": entrada_broker.strftime("%H:%M:%S"),
            "segundos_para_entrar": max(0, round(seg_para_entrar, 1)),
            "timezone": "UTC-6",
            
            "duracion_min": duracion_min,
            "total_escaneados": activos_analizados,
            "señales_encontradas": len(resultados),
            "mejores_activos": resultados[:10],
            "mensaje_entrada": f"Entrar a {mejor['nombre']} a las {entrada_broker.strftime('%H:%M:%S')}",
        })
    else:
        return jsonify({
            "ok": False,
            "mensaje": "No se encontraron señales con confirmación",
            "total_escaneados": activos_analizados,
            "hora_actual": actual_broker.strftime("%H:%M:%S"),
            "hora_entrada": entrada_broker.strftime("%H:%M:%S"),
            "segundos_para_entrar": max(0, round(seg_para_entrar, 1)),
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("="*80)
    print("  IQ Option Bot API  v15.0 - 1 VELA + 2 CONFIRMACIONES")
    print(f"  http://0.0.0.0:{port}")
    print("="*80)
    print("")
    print("  🔥 NUEVA LÓGICA DE ANÁLISIS:")
    print("     ✅ Toma SOLO la última vela CERRADA")
    print("     ✅ Busca esa vela en el historial (1000 velas)")
    print("     ✅ CONFIRMA 2 VECES la coincidencia")
    print("     ✅ Predice cómo terminará la vela EN
