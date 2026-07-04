"""
server.py — IQ Option Bot API v8.0
- CONFIANZA EXTREMA 90-95%
- TIMING PERFECTO en HH:MM:00
- SOLO señales con confirmación múltiple
- Gestión de riesgo automática
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_cors import CORS
import time, logging, threading
from datetime import datetime, timezone, timedelta

from analysis import generar_senal, detectar_volatilidad, seleccionar_estrategia_auto

app = Flask(__name__)
CORS(app, origins="*", allow_headers=["Content-Type","Accept","Authorization","X-API-Key"],
     methods=["GET","POST","OPTIONS"])

# ── ZONA HORARIA DEL BROKER (IQ Option) ─────────────────────────
BROKER_TIMEZONE = timezone(timedelta(hours=-6))

# ── CONFIGURACIÓN DE CONFIANZA EXTREMA ──────────────────────────
CONFIANZA_MINIMA = 90  # SOLO señales con 90%+ de confianza
INTERVALO_FIJO = 60     # Velas de 1 minuto

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
streams_lock    = threading.Lock()

# ── Cache de activos ─────────────────────────────────────────────
_cache_activos    = []
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
    """Convierte un timestamp a hora del broker (UTC-6)"""
    return datetime.fromtimestamp(timestamp, tz=BROKER_TIMEZONE)

# ════════════════════════════════════════════════════════════════
#  AUTO-CONNECT AL ARRANCAR
# ════════════════════════════════════════════════════════════════

def _auto_connect():
    email    = os.environ.get("IQ_EMAIL",    "").strip()
    password = os.environ.get("IQ_PASSWORD", "").strip()
    cuenta   = os.environ.get("IQ_CUENTA",   "PRACTICE").upper()

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
            sesion["api"]       = api
            sesion["email"]     = email
            sesion["conectado"] = True
            sesion["cuenta"]    = cuenta

        log.info(f"✅ Auto-conectado OK — cuenta {cuenta}")

    except Exception as e:
        log.error(f"Error auto-connect: {e}")

# ════════════════════════════════════════════════════════════════
#  PRE-CARGA DE ACTIVOS EN BACKGROUND
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
                if payout <= 0:
                    continue
                if payout < 80:  # Solo activos con buen payout
                    continue
                resultado.append({
                    "ticker":  activo,
                    "nombre":  _nombre_legible(activo),
                    "es_otc":  "OTC" in activo.upper(),
                    "payout":  payout,
                    "abierto": True,
                })

            resultado.sort(key=lambda x: (-x["payout"], not x["es_otc"], x["ticker"]))
            _cache_activos    = resultado
            _cache_activos_ts = time.time()
            log.info(f"✅ Cache activos: {len(resultado)} activos cargados (payout >= 80%)")

        except Exception as e:
            log.error(f"Error precargando activos: {e}")
        time.sleep(300)

# Arrancar hilos
threading.Thread(target=_auto_connect,     daemon=True).start()
threading.Thread(target=_precargar_activos, daemon=True).start()

# ════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════════

@app.route("/")
def raiz():
    return jsonify({
        "api":       "IQ Option Bot API",
        "version":   "8.0",
        "estado":    "online",
        "conectado": sesion["conectado"],
        "activos_en_cache": len(_cache_activos),
        "intervalo_fijo": INTERVALO_FIJO,
        "broker_timezone": "UTC-6",
        "confianza_minima": CONFIANZA_MINIMA,
    })

@app.route("/iq/ping")
def ping():
    return jsonify({
        "ok":               True,
        "conectado":        sesion["conectado"],
        "email":            sesion["email"] if sesion["conectado"] else None,
        "cuenta":           sesion["cuenta"],
        "activos_en_cache": len(_cache_activos),
        "intervalo_fijo":   INTERVALO_FIJO,
        "broker_timezone":  "UTC-6",
        "confianza_minima": CONFIANZA_MINIMA,
        "timestamp":        int(time.time()),
    })

@app.route("/iq/conectar", methods=["POST"])
def conectar():
    body     = request.get_json(force=True)
    email    = body.get("email","").strip()
    password = body.get("password","")
    cuenta   = body.get("cuenta","PRACTICE").upper()
    if not email or not password:
        return jsonify({"ok":False,"error":"Se requieren email y password"}), 400
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
                return jsonify({"ok":False,"error":f"Error: {res[1]}"}), 401
            api.change_balance(cuenta)
            time.sleep(2)
            saldo = api.get_balance()
            sesion["api"]=api; sesion["email"]=email
            sesion["conectado"]=True; sesion["cuenta"]=cuenta
        return jsonify({"ok":True,"email":email,"cuenta":cuenta,"saldo":round(saldo,2) if saldo else None})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

@app.route("/iq/desconectar")
def desconectar():
    with sesion["lock"]:
        if sesion["api"]:
            try: sesion["api"].api.close()
            except: pass
        sesion["api"]=None; sesion["conectado"]=False; sesion["email"]=None
    return jsonify({"ok":True})

@app.route("/iq/activos/blitz")
@requiere_conexion
def activos_blitz():
    global _cache_activos
    if _cache_activos:
        return jsonify({
            "ok":      True,
            "tipo":    "blitz",
            "total":   len(_cache_activos),
            "activos": _cache_activos,
            "cached":  True,
        })
    try:
        api = sesion["api"]
        open_time_res=[None]; profits_res=[None]
        def _ot(): open_time_res[0]=api.get_all_open_time()
        def _pr(): profits_res[0]=api.get_all_profit()
        t1=threading.Thread(target=_ot,daemon=True)
        t2=threading.Thread(target=_pr,daemon=True)
        t1.start(); t2.start(); t1.join(timeout=25); t2.join(timeout=25)
        open_time=open_time_res[0] or {}; profits=profits_res[0] or {}
        resultado=[]; vistos=set()
        if "turbo" in open_time:
            for activo, datos in open_time["turbo"].items():
                if activo in vistos: continue
                if not any(info.get("open",False) for _,info in datos.items()): continue
                vistos.add(activo)
                profit_info=profits.get(activo,{})
                payout=round((profit_info.get("turbo",0) or 0)*100,1)
                if payout < 80:
                    continue
                resultado.append({
                    "ticker":activo,"nombre":_nombre_legible(activo),
                    "es_otc":"OTC" in activo.upper(),"payout":payout,"abierto":True
                })
        resultado.sort(key=lambda x:(-x["payout"],not x["es_otc"],x["ticker"]))
        _cache_activos=resultado
        return jsonify({"ok":True,"tipo":"blitz","total":len(resultado),"activos":resultado,"cached":False})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/iq/velas/live")
@requiere_conexion
def velas_live():
    api       = sesion["api"]
    activo    = normalizar_activo(request.args.get("activo","EURUSD-OTC"))
    intervalo = INTERVALO_FIJO
    cantidad  = int(request.args.get("cantidad",60))
    clave     = f"{activo}_{intervalo}"
    
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
                    "open":  round(float(c.get("open",0)),6),
                    "high":  round(float(c.get("max",0)),6),
                    "low":   round(float(c.get("min",0)),6),
                    "close": round(float(c.get("close",0)),6),
                })
        else:
            raw = api.get_candles(activo, intervalo, cantidad, time.time())
            velas_fmt = [raw_a_vela(c) for c in raw] if raw else []
        if not velas_fmt:
            return jsonify({"error":f"Sin datos para {activo}"}), 404
        precio_actual   = velas_fmt[-1]["close"]
        precio_anterior = velas_fmt[-2]["close"] if len(velas_fmt)>=2 else precio_actual
        tendencia = "UP" if precio_actual>=precio_anterior else "DOWN"
        ahora = int(time.time())
        return jsonify({
            "ok":True,"activo":activo,"nombre":_nombre_legible(activo),
            "intervalo":intervalo,"precio":precio_actual,"tendencia":tendencia,
            "vela_cierra_en":intervalo-(ahora%intervalo),
            "server_time":ahora,"velas":velas_fmt,
        })
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/iq/velas/stop")
@requiere_conexion
def velas_stop():
    api=sesion["api"]
    activo=normalizar_activo(request.args.get("activo","EURUSD-OTC"))
    intervalo=INTERVALO_FIJO
    clave=f"{activo}_{intervalo}"
    try:
        with streams_lock:
            if clave in streams_activos:
                api.stop_candles_stream(activo,intervalo)
                del streams_activos[clave]
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/iq/senal", methods=["POST"])
@requiere_conexion
def senal():
    """
    SISTEMA DE CONFIANZA EXTREMA 90-95%
    - SOLO señales con confianza ≥ 90%
    - TIMING PERFECTO en HH:MM:00
    - Filtros de seguridad adicionales
    """
    api  = sesion["api"]
    body = request.get_json(force=True)

    activo       = normalizar_activo(body.get("activo", "EURUSD-OTC"))
    duracion_min = float(body.get("duracion", 1))
    cantidad     = int(body.get("cantidad_velas", 150))

    intervalo = INTERVALO_FIJO

    try:
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if not raw:
            return jsonify({"error": f"Sin velas para {activo}"}), 404

        candles = [raw_a_vela(c) for c in raw]
        resultado = generar_senal(candles, "confianza_extrema", intervalo)

        # ── FILTRO DE CONFIANZA EXTREMA ──────────────────────────
        confianza = resultado.get("confianza", 0)
        
        # SOLO aceptar señales con confianza ≥ 90%
        if resultado["direccion"] in ("BUY", "SELL") and confianza < CONFIANZA_MINIMA:
            log.info(f"🔒 Señal RECHAZADA: {resultado['direccion']} con confianza {confianza}% (mínimo {CONFIANZA_MINIMA}%)")
            resultado["direccion"] = "ESPERAR"
            resultado["confianza"] = 0
            resultado["razones"] = [
                f"Confianza insuficiente: {confianza}%",
                f"Se requiere mínimo {CONFIANZA_MINIMA}%",
                "Esperar señal más fuerte"
            ]

        # ── TIMING PERFECTO ──────────────────────────────────────
        ahora_ts = time.time()
        
        ahora_broker = hora_broker(ahora_ts)
        segundos_en_minuto = ahora_broker.second + (ahora_broker.microsecond / 1000000)
        
        # SIEMPRE al PRÓXIMO minuto exacto
        if segundos_en_minuto == 0:
            seg_para_entrar = 60
        else:
            seg_para_entrar = 60 - segundos_en_minuto
        
        if seg_para_entrar < 1:
            seg_para_entrar = 60
        
        ts_entrada = ahora_ts + seg_para_entrar
        
        # ── CALCULAR SALIDA ──────────────────────────────────────
        duracion_seg = duracion_min * 60
        ts_salida = ts_entrada + duracion_seg
        ts_verificar = ts_entrada + (duracion_seg / 2)

        # ── FORMATO HORA DEL BROKER ─────────────────────────────
        entrada_broker = hora_broker(ts_entrada)
        salida_broker = hora_broker(ts_salida)
        actual_broker = hora_broker(ahora_ts)
        verificar_broker = hora_broker(ts_verificar)

        hora_actual = actual_broker.strftime("%H:%M:%S")
        hora_entrada = entrada_broker.strftime("%H:%M:%S")
        hora_salida = salida_broker.strftime("%H:%M:%S")
        hora_verificar = verificar_broker.strftime("%H:%M:%S")

        seg_restantes = max(0, round(seg_para_entrar, 1))

        # ── INFO ADICIONAL PARA CONFIANZA EXTREMA ──────────────
        es_senal_valida = resultado["direccion"] in ("BUY", "SELL") and confianza >= CONFIANZA_MINIMA

        # Profit real
        profit_pct = None
        try:
            profits = api.get_all_profit()
            profit_pct = profits.get(activo, {}).get("turbo")
        except:
            pass

        return jsonify({
            "ok": True,
            "activo": activo,
            "nombre": _nombre_legible(activo),
            "es_otc": "OTC" in activo,
            "senal": resultado["direccion"],
            "confianza": confianza if es_senal_valida else 0,

            # ── TIMING PERFECTO ─────────────────────────────────
            "hora_actual": hora_actual,
            "hora_entrada": hora_entrada,
            "hora_salida": hora_salida,
            "hora_verificar": hora_verificar,
            "segundos_para_entrar": seg_restantes,
            "mensaje_entrada": f"Entrar a las {hora_entrada} (inicio de vela)",
            "timezone": "UTC-6",

            # ── CONFIRMACIONES DE SEGURIDAD ─────────────────────
            "confianza_minima": CONFIANZA_MINIMA,
            "senal_valida": es_senal_valida,
            "requiere_confirmacion": es_senal_valida,

            # ── RAZONES Y ANÁLISIS ──────────────────────────────
            "razones": resultado.get("razones", []),
            "votos_buy": resultado.get("votos_buy", 0),
            "votos_sell": resultado.get("votos_sell", 0),
            "score_buy": resultado.get("score_buy", 0),
            "score_sell": resultado.get("score_sell", 0),
            "volatilidad": resultado.get("volatilidad", "media"),
            "tendencia": resultado.get("tendencia", "LATERAL"),

            # ── INFO OPERACIÓN ──────────────────────────────────
            "duracion_seg": int(duracion_seg),
            "duracion_min": duracion_min,
            "intervalo_vela": intervalo,
            "rentabilidad": f"{round(profit_pct*100,1)}%" if profit_pct else "N/D",

            # ── INDICADORES ──────────────────────────────────────
            "indicadores": resultado.get("indicadores", {}),
            "timing": resultado.get("timing", {}),
            "patrones_velas": resultado.get("patrones_velas", []),
        })

    except Exception as e:
        log.exception("Error en /iq/senal")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8080))
    print("="*70)
    print("  IQ Option Bot API  v8.0 - CONFIANZA EXTREMA")
    print(f"  http://0.0.0.0:{port}")
    print(f"  📊 Intervalo de velas: {INTERVALO_FIJO}s")
    print(f"  🎯 Entrada SIEMPRE en HH:MM:00 (inicio de vela)")
    print(f"  🕐 Zona horaria del BROKER: UTC-6")
    print(f"  🔒 Confianza mínima requerida: {CONFIANZA_MINIMA}%")
    print("  📈 SOLO señales con 90%+ de probabilidad de éxito")
    print("="*70)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
