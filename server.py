"""
server.py — IQ Option Bot API v7.0
- Auto-conexión al arrancar usando IQ_EMAIL + IQ_PASSWORD de Railway
- Sin login en el frontend
- Velas en tiempo real (Blitz)
- Activos Blitz con payout
- Señales con hora de entrada

Variables de entorno Railway:
  IQ_EMAIL     → tu email de IQ Option
  IQ_PASSWORD  → tu contraseña de IQ Option
  IQ_CUENTA    → PRACTICE (default) o REAL
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_cors import CORS
import time, logging, threading
from datetime import datetime, timezone

from analysis import generar_senal, detectar_volatilidad, seleccionar_estrategia_auto

app = Flask(__name__)
CORS(app, origins="*", allow_headers=["Content-Type","Accept","Authorization","X-API-Key"],
     methods=["GET","POST","OPTIONS"])

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


# ════════════════════════════════════════════════════════════════
#  AUTO-CONNECT AL ARRANCAR (usa env vars de Railway)
# ════════════════════════════════════════════════════════════════

def _auto_connect():
    email    = os.environ.get("IQ_EMAIL",    "").strip()
    password = os.environ.get("IQ_PASSWORD", "").strip()
    cuenta   = os.environ.get("IQ_CUENTA",   "PRACTICE").upper()

    if not email or not password:
        log.warning("⚠️  Sin IQ_EMAIL/IQ_PASSWORD en env vars. Usa POST /iq/conectar manualmente.")
        return

    log.info(f"🔄 Auto-conectando a IQ Option como {email} [{cuenta}]...")
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
            log.error(f"❌ Auto-connect falló: {resultado[1]}")
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
        log.error(f"❌ Error auto-connect: {e}")


threading.Thread(target=_auto_connect, daemon=True).start()


# ════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════

def requiere_conexion(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not sesion["conectado"] or sesion["api"] is None:
            return jsonify({
                "error": "No hay sesión activa",
                "hint":  "Agrega IQ_EMAIL e IQ_PASSWORD en las variables de entorno de Railway, o llama POST /iq/conectar"
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


def _nombre_legible(ticker):
    """EURUSD-OTC → EUR/USD (OTC)   |   GBPUSD → GBP/USD"""
    t = ticker
    es_otc = t.endswith("-OTC")
    if es_otc:
        t = t[:-4]
    # pares de 6 letras → agregar /
    if len(t) == 6 and t.isalpha():
        t = t[:3] + "/" + t[3:]
    elif len(t) == 7 and "/" not in t:
        t = t[:3] + "/" + t[3:]
    if es_otc:
        t += " (OTC)"
    return t


# ════════════════════════════════════════════════════════════════
#  ENDPOINTS PÚBLICOS
# ════════════════════════════════════════════════════════════════

@app.route("/")
def raiz():
    return jsonify({
        "api":      "IQ Option Bot API",
        "version":  "7.0",
        "estado":   "online",
        "conectado": sesion["conectado"],
        "endpoints": [
            "GET  /iq/ping            — estado de conexión",
            "POST /iq/conectar        — { email, password, cuenta }",
            "GET  /iq/activos/blitz   — activos OTC+normales con payout",
            "GET  /iq/velas/live      — ?activo=EURUSD-OTC&intervalo=5&cantidad=60",
            "GET  /iq/velas/stop      — ?activo=EURUSD-OTC&intervalo=5",
            "POST /iq/senal           — { activo, intervalo, duracion }",
            "GET  /iq/desconectar     — cierra sesión",
        ]
    })


@app.route("/iq/ping")
def ping():
    """Endpoint público — el frontend lo llama para saber si el backend está conectado."""
    return jsonify({
        "ok":        True,
        "conectado": sesion["conectado"],
        "email":     sesion["email"] if sesion["conectado"] else None,
        "cuenta":    sesion["cuenta"],
        "timestamp": int(time.time()),
    })


# ════════════════════════════════════════════════════════════════
#  LOGIN MANUAL (opcional — si no usas env vars)
# ════════════════════════════════════════════════════════════════

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
                try:    res[0], res[1] = api.connect()
                except Exception as ex: res[0]=False; res[1]=str(ex)

            t = threading.Thread(target=_c, daemon=True)
            t.start()
            t.join(timeout=15)

            if t.is_alive() or not res[0]:
                return jsonify({"ok":False,"error":f"Error de conexión: {res[1]}"}), 401

            api.change_balance(cuenta)
            time.sleep(2)

            saldo = api.get_balance()
            sesion["api"]       = api
            sesion["email"]     = email
            sesion["conectado"] = True
            sesion["cuenta"]    = cuenta

        return jsonify({"ok":True,"email":email,"cuenta":cuenta,"saldo":round(saldo,2) if saldo else None})

    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500


@app.route("/iq/desconectar")
def desconectar():
    with sesion["lock"]:
        if sesion["api"]:
            try: sesion["api"].api.close()
            except: pass
        sesion["api"] = None
        sesion["conectado"] = False
        sesion["email"] = None
    return jsonify({"ok":True})


# ════════════════════════════════════════════════════════════════
#  ACTIVOS BLITZ (OTC + NORMALES con payout)
# ════════════════════════════════════════════════════════════════

@app.route("/iq/activos/blitz")
@requiere_conexion
def activos_blitz():
    """
    Devuelve TODOS los activos Blitz (turbo) abiertos en este momento,
    incluyendo OTC y normales, con su payout real.
    """
    api = sesion["api"]
    try:
        # Obtener activos abiertos y profits en paralelo
        open_time_res = [None]
        profits_res   = [None]

        def _ot():
            open_time_res[0] = api.get_all_open_time()
        def _pr():
            profits_res[0]   = api.get_all_profit()

        t1 = threading.Thread(target=_ot, daemon=True)
        t2 = threading.Thread(target=_pr, daemon=True)
        t1.start(); t2.start()
        t1.join(timeout=20); t2.join(timeout=20)

        open_time = open_time_res[0] or {}
        profits   = profits_res[0]   or {}

        resultado = []
        vistos = set()
        tipo_iq = "turbo"

        if tipo_iq in open_time:
            for activo, datos in open_time[tipo_iq].items():
                if activo in vistos:
                    continue

                # Verificar que al menos una expiración esté abierta
                abierto = any(
                    info.get("open", False)
                    for _, info in datos.items()
                )
                if not abierto:
                    continue

                vistos.add(activo)
                es_otc = "OTC" in activo.upper()

                profit_info = profits.get(activo, {})
                payout_raw  = profit_info.get("turbo", 0) or 0
                payout      = round(payout_raw * 100, 1)

                resultado.append({
                    "ticker":  activo,
                    "nombre":  _nombre_legible(activo),
                    "es_otc":  es_otc,
                    "payout":  payout,
                    "abierto": True,
                })

        # Orden: mayor payout primero, luego OTC antes que normales
        resultado.sort(key=lambda x: (-x["payout"], not x["es_otc"], x["ticker"]))

        return jsonify({
            "ok":     True,
            "tipo":   "blitz",
            "total":  len(resultado),
            "activos": resultado,
        })

    except Exception as e:
        log.exception("Error en /iq/activos/blitz")
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  VELAS EN TIEMPO REAL
# ════════════════════════════════════════════════════════════════

@app.route("/iq/velas/live")
@requiere_conexion
def velas_live():
    """
    Devuelve velas en tiempo real del broker.
    El frontend llama esto cada 1 segundo para actualizar el gráfico.

    Params:
      activo    → ticker IQ Option (ej: EURUSD-OTC)
      intervalo → tamaño de vela en segundos (5, 10, 15, 30, 60)
      cantidad  → cuántas velas mostrar (default 60)
    """
    api       = sesion["api"]
    activo    = normalizar_activo(request.args.get("activo",    "EURUSD-OTC"))
    intervalo = int(request.args.get("intervalo", 5))
    cantidad  = int(request.args.get("cantidad",  60))
    clave     = f"{activo}_{intervalo}"

    # Validar que el intervalo sea soportado por IQ Option
    INTERVALOS_VALIDOS = [1,5,10,15,30,60,120,300,600,900,1800,3600]
    if intervalo not in INTERVALOS_VALIDOS:
        intervalo = 5

    try:
        with streams_lock:
            if clave not in streams_activos:
                api.start_candles_stream(activo, intervalo, cantidad)
                streams_activos[clave] = True
                time.sleep(1.0)

        # Leer buffer en tiempo real
        rt = api.get_realtime_candles(activo, intervalo)
        velas_fmt = []

        if rt and len(rt) > 0:
            for ts in sorted(rt.keys())[-cantidad:]:
                c = rt[ts]
                velas_fmt.append({
                    "timestamp": int(ts),
                    "open":  round(float(c.get("open",  0)), 6),
                    "high":  round(float(c.get("max",   0)), 6),
                    "low":   round(float(c.get("min",   0)), 6),
                    "close": round(float(c.get("close", 0)), 6),
                })
        else:
            raw = api.get_candles(activo, intervalo, cantidad, time.time())
            velas_fmt = [raw_a_vela(c) for c in raw] if raw else []

        if not velas_fmt:
            return jsonify({"error": f"Sin datos para {activo}"}), 404

        precio_actual   = velas_fmt[-1]["close"]
        precio_anterior = velas_fmt[-2]["close"] if len(velas_fmt) >= 2 else precio_actual
        tendencia       = "UP" if precio_actual >= precio_anterior else "DOWN"

        ahora = int(time.time())
        seg_restantes = intervalo - (ahora % intervalo)

        return jsonify({
            "ok":             True,
            "activo":         activo,
            "nombre":         _nombre_legible(activo),
            "intervalo":      intervalo,
            "precio":         precio_actual,
            "tendencia":      tendencia,
            "vela_cierra_en": seg_restantes,
            "server_time":    ahora,
            "velas":          velas_fmt,
        })

    except Exception as e:
        log.exception(f"Error velas/live {activo}")
        return jsonify({"error": str(e)}), 500


@app.route("/iq/velas/stop")
@requiere_conexion
def velas_stop():
    api       = sesion["api"]
    activo    = normalizar_activo(request.args.get("activo",    "EURUSD-OTC"))
    intervalo = int(request.args.get("intervalo", 5))
    clave     = f"{activo}_{intervalo}"
    try:
        with streams_lock:
            if clave in streams_activos:
                api.stop_candles_stream(activo, intervalo)
                del streams_activos[clave]
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  SEÑAL BUY / SELL
# ════════════════════════════════════════════════════════════════

@app.route("/iq/senal", methods=["POST"])
@requiere_conexion
def senal():
    """
    POST /iq/senal
    Body: {
      "activo":    "EURUSD-OTC",
      "intervalo": 5,          ← tamaño de vela en segundos
      "duracion":  1,          ← expiración en minutos
      "cantidad_velas": 150    ← velas para el análisis
    }
    """
    api  = sesion["api"]
    body = request.get_json(force=True)

    activo    = normalizar_activo(body.get("activo",    "EURUSD-OTC"))
    intervalo = int(body.get("intervalo",  5))
    duracion  = int(body.get("duracion",   1))
    cantidad  = int(body.get("cantidad_velas", 150))

    try:
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if not raw:
            return jsonify({"error": f"Sin velas para {activo}"}), 404

        candles   = [raw_a_vela(c) for c in raw]
        resultado = generar_senal(candles, "auto", intervalo)

        if "error" in resultado:
            return jsonify(resultado), 400

        ahora = datetime.now(timezone.utc)
        prox  = intervalo - (int(time.time()) % intervalo)

        # Profit real
        profit_pct = None
        try:
            profits    = api.get_all_profit()
            p_info     = profits.get(activo, {})
            profit_pct = p_info.get("turbo")
        except:
            pass

        return jsonify({
            "ok":              True,
            "activo":          activo,
            "nombre":          _nombre_legible(activo),
            "es_otc":          "OTC" in activo,
            "senal":           resultado["direccion"],
            "hora_entrada":    ahora.strftime("%H:%M:%S"),
            "hora_utc":        ahora.strftime("%H:%M:%S UTC"),
            "proxima_vela_en": prox,
            "duracion_min":    duracion,
            "intervalo_vela":  intervalo,
            "rentabilidad":    f"{round(profit_pct*100,1)}%" if profit_pct else "N/D",
            "volatilidad":     resultado.get("volatilidad","media"),
            "tendencia":       resultado.get("tendencia","LATERAL"),
            "timing":          resultado.get("timing",{}),
            "confianza":       resultado.get("confianza", 0),
            "votos_buy":       resultado.get("votos_buy", 0),
            "votos_sell":      resultado.get("votos_sell", 0),
            "razones":         resultado.get("razones", []),
            "indicadores":     resultado.get("indicadores", {}),
        })

    except Exception as e:
        log.exception("Error en /iq/senal")
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  ARRANQUE
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("=" * 60)
    print("  IQ Option Bot API  v7.0")
    print(f"  http://0.0.0.0:{port}")
    print("  Auto-connect: IQ_EMAIL + IQ_PASSWORD en env vars")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
