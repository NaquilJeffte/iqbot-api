"""
server.py — IQ Option Bot API v6.0
Acceso completo con solo email + password de IQ Option.
Sin API Key en el frontend — seguridad real.

Endpoints:
  POST /iq/conectar          → login con email + contraseña IQ Option
  GET  /iq/estado            → estado de conexión, saldo real y demo
  GET  /iq/activos           → activos abiertos (OTC y normales)
  GET  /iq/velas             → velas históricas
  GET  /iq/velas/live        → velas en tiempo real (stream)
  POST /iq/senal             → señal BUY/SELL con análisis técnico completo
  GET  /iq/profit            → rentabilidad % de un activo
  GET  /iq/top_activos       → mejores activos por rentabilidad
  GET  /iq/desconectar       → cierra la sesión
  GET  /demo/senal           → demo sin login (para probar sin cuenta)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import logging
import threading
from datetime import datetime, timezone

from analysis import generar_senal, detectar_volatilidad, seleccionar_estrategia_auto

app = Flask(__name__)
CORS(app, origins="*", allow_headers=["Content-Type", "Accept", "Authorization", "X-API-Key"], methods=["GET", "POST", "OPTIONS"])

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        from flask import Response
        res = Response()
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept, Authorization, X-API-Key"
        return res

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept, Authorization, X-API-Key"
    return response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Sesión global IQ ─────────────────────────────────────────────
sesion = {"api": None, "email": None, "conectado": False, "lock": threading.Lock()}

IQ_TIMEOUT = 15


# ════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════

def requiere_conexion(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not sesion["conectado"] or sesion["api"] is None:
            return jsonify({
                "error": "No hay sesión activa",
                "hint":  "Llama primero a POST /iq/conectar con tu email y password de IQ Option"
            }), 403
        return f(*args, **kwargs)
    return wrapper


def raw_a_vela(c):
    return {
        "timestamp": c["from"],
        "datetime":  datetime.fromtimestamp(c["from"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "open":  c["open"],
        "high":  c["max"],
        "low":   c["min"],
        "close": c["close"],
        "volumen": c.get("volume", 0),
        "max": c["max"],
        "min": c["min"],
    }


# ════════════════════════════════════════════════════════════════
#  Endpoint raíz
# ════════════════════════════════════════════════════════════════

@app.route("/")
def raiz():
    return jsonify({
        "api":     "IQ Option Bot API",
        "version": "6.0",
        "estado":  "online",
        "acceso":  "Solo necesitas tu email y password de IQ Option",
        "endpoints": [
            "POST /iq/conectar       — { email, password, cuenta }",
            "GET  /iq/estado         — saldo real y demo",
            "GET  /iq/activos        — activos disponibles",
            "GET  /iq/velas          — ?activo=EURUSD&intervalo=60&cantidad=100",
            "GET  /iq/velas/live     — ?activo=EURUSD&intervalo=60",
            "POST /iq/senal          — { activo, intervalo, duracion, estrategia }",
            "GET  /iq/profit         — ?activo=EURUSD",
            "GET  /iq/top_activos    — mejores activos por rentabilidad",
            "GET  /iq/desconectar    — cierra sesión",
            "GET  /demo/senal        — ?activo=EURUSD&intervalo=60",
        ]
    })


# ════════════════════════════════════════════════════════════════
#  LOGIN — solo email + password IQ Option
# ════════════════════════════════════════════════════════════════

@app.route("/iq/conectar", methods=["POST"])
def conectar():
    """
    POST /iq/conectar
    Body: { "email": "tu@gmail.com", "password": "tupassword", "cuenta": "PRACTICE" }
    cuenta: "PRACTICE" (demo) o "REAL"
    """
    body     = request.get_json(force=True)
    email    = body.get("email", "").strip()
    password = body.get("password", "")
    cuenta   = body.get("cuenta", "PRACTICE").upper()

    if not email or not password:
        return jsonify({"ok": False, "error": "Se requieren email y password"}), 400

    try:
        from iqoptionapi.stable_api import IQ_Option
        import threading as _th

        with sesion["lock"]:
            if sesion["api"]:
                try:
                    sesion["api"].api.close()
                except:
                    pass

            api = IQ_Option(email, password)

            # Conexión con timeout real de 15 segundos
            resultado_conn = [None, None]
            def _conectar():
                try:
                    resultado_conn[0], resultado_conn[1] = api.connect()
                except Exception as ex:
                    resultado_conn[0] = False
                    resultado_conn[1] = str(ex)

            t = _th.Thread(target=_conectar, daemon=True)
            t.start()
            t.join(timeout=15)

            if t.is_alive():
                return jsonify({"ok": False, "error": "IQ Option tardó demasiado en responder. Intenta de nuevo."}), 504

            ok, razon = resultado_conn
            if not ok:
                msg = str(razon)
                if "2fa" in msg.lower() or "token" in msg.lower():
                    return jsonify({"ok": False, "error": "Tu cuenta tiene verificación en 2 pasos. Desactívala en IQ Option temporalmente."}), 401
                return jsonify({"ok": False, "error": "Email o contraseña incorrectos. Verifica tus credenciales en iqoption.com"}), 401

            api.change_balance(cuenta)
            time.sleep(0.5)  # mínimo necesario para que IQ actualice el balance

            saldo = api.get_balance()
            modo  = api.get_balance_mode()

            # Obtener ambos saldos
            saldos = {}
            try:
                raw = api.get_balances()
                for b in raw.get("msg", []):
                    tipo = b.get("type")
                    amt  = b.get("amount", 0)
                    if tipo == 1:
                        saldos["real"] = round(amt, 2)
                    elif tipo == 4:
                        saldos["demo"] = round(amt, 2)
            except:
                pass

            sesion["api"]       = api
            sesion["email"]     = email
            sesion["conectado"] = True

        return jsonify({
            "ok":      True,
            "email":   email,
            "cuenta":  modo or cuenta,
            "saldo":   round(saldo, 2) if saldo else None,
            "saldos":  saldos,
            "mensaje": f"Conectado a IQ Option — cuenta {modo or cuenta}"
        })

    except Exception as e:
        log.exception("Error en /iq/conectar")
        return jsonify({"ok": False, "error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  ESTADO
# ════════════════════════════════════════════════════════════════

@app.route("/iq/estado")
@requiere_conexion
def estado():
    api = sesion["api"]
    try:
        conectado = api.check_connect
        saldo     = api.get_balance() if conectado else None
        modo      = api.get_balance_mode() if conectado else None

        saldos = {}
        try:
            raw = api.get_balances()
            for b in raw.get("msg", []):
                tipo = b.get("type")
                amt  = b.get("amount", 0)
                if tipo == 1:
                    saldos["real"] = round(amt, 2)
                elif tipo == 4:
                    saldos["demo"] = round(amt, 2)
        except:
            pass

        return jsonify({
            "ok":            True,
            "conectado":     conectado,
            "email":         sesion["email"],
            "cuenta_activa": modo,
            "saldo_activo":  round(saldo, 2) if saldo else None,
            "saldos":        saldos,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  DESCONECTAR
# ════════════════════════════════════════════════════════════════

@app.route("/iq/desconectar")
def desconectar():
    with sesion["lock"]:
        if sesion["api"]:
            try:
                sesion["api"].api.close()
            except:
                pass
        sesion["api"]       = None
        sesion["conectado"] = False
        sesion["email"]     = None
    return jsonify({"ok": True, "mensaje": "Sesión cerrada"})


# ════════════════════════════════════════════════════════════════
#  ACTIVOS
# ════════════════════════════════════════════════════════════════

@app.route("/iq/activos")
@requiere_conexion
def activos():
    api     = sesion["api"]
    tipo    = request.args.get("tipo", "all")
    solo_ab = request.args.get("solo_abiertos", "1") == "1"

    try:
        open_time = api.get_all_open_time()
        tipos_map = {
            "binary":  ["turbo", "binary"],
            "digital": ["digital"],
            "all":     ["turbo", "binary", "digital"],
        }
        tipos_check = tipos_map.get(tipo, tipos_map["all"])

        resultado = {}
        for t in tipos_check:
            if t not in open_time:
                continue
            for activo, datos in open_time[t].items():
                es_otc = "OTC" in activo.upper()
                for exp, info in datos.items():
                    abierto = info.get("open", False)
                    if solo_ab and not abierto:
                        continue
                    if activo not in resultado:
                        resultado[activo] = {"es_otc": es_otc, "tipos": {}}
                    resultado[activo]["tipos"][f"{t}_{exp}"] = {
                        "abierto":    abierto,
                        "tipo":       t,
                        "expiracion": exp,
                    }

        return jsonify({
            "ok":     True,
            "total":  len(resultado),
            "activos": resultado,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  VELAS HISTÓRICAS
# ════════════════════════════════════════════════════════════════

@app.route("/iq/velas")
@requiere_conexion
def velas():
    api       = sesion["api"]
    activo    = request.args.get("activo",    "EURUSD")
    intervalo = int(request.args.get("intervalo", 60))
    cantidad  = int(request.args.get("cantidad",  100))

    try:
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if raw is None:
            return jsonify({"error": f"Sin datos para {activo}"}), 404

        velas_fmt = [raw_a_vela(c) for c in raw]
        return jsonify({
            "ok":        True,
            "activo":    activo,
            "intervalo": f"{intervalo}s",
            "cantidad":  len(velas_fmt),
            "velas":     velas_fmt,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  VELAS EN TIEMPO REAL
# ════════════════════════════════════════════════════════════════

@app.route("/iq/velas/live")
@requiere_conexion
def velas_live():
    api       = sesion["api"]
    activo    = request.args.get("activo",    "EURUSD")
    intervalo = int(request.args.get("intervalo", 60))

    try:
        api.start_candles_stream(activo, intervalo, 10)
        time.sleep(2)

        rt = api.get_realtime_candles(activo, intervalo)
        if not rt:
            raw = api.get_candles(activo, intervalo, 5, time.time())
            velas_fmt = [raw_a_vela(c) for c in raw] if raw else []
        else:
            velas_fmt = []
            for ts in sorted(rt.keys())[-5:]:
                c = rt[ts]
                velas_fmt.append({
                    "timestamp": ts,
                    "datetime":  datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "open":  c.get("open", 0),
                    "high":  c.get("max", 0),
                    "low":   c.get("min", 0),
                    "close": c.get("close", 0),
                    "max":   c.get("max", 0),
                    "min":   c.get("min", 0),
                })

        return jsonify({
            "ok":        True,
            "activo":    activo,
            "intervalo": f"{intervalo}s",
            "live":      True,
            "velas":     velas_fmt,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  SEÑAL BUY/SELL
# ════════════════════════════════════════════════════════════════

@app.route("/iq/senal", methods=["POST"])
@requiere_conexion
def senal():
    """
    POST /iq/senal
    Body: { "activo": "EURUSD", "intervalo": 60, "duracion": 1, "estrategia": "auto" }
    estrategia: "auto" | "fibonacci" | "bollinger" | "tendencia" | "macd" | "rsi"
    """
    api  = sesion["api"]
    body = request.get_json(force=True)

    activo     = body.get("activo",    "EURUSD")
    intervalo  = int(body.get("intervalo",  60))
    duracion   = int(body.get("duracion",    1))
    cantidad   = int(body.get("cantidad_velas", 100))
    estrategia = body.get("estrategia", "auto")

    try:
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if raw is None:
            return jsonify({"error": f"Sin velas para {activo}"}), 404

        candles   = [raw_a_vela(c) for c in raw]
        resultado = generar_senal(candles, estrategia)
        if "error" in resultado:
            return jsonify(resultado), 400

        es_otc = "OTC" in activo.upper()
        ahora  = datetime.now(timezone.utc)
        prox   = intervalo - (int(time.time()) % intervalo)

        abierto = None
        try:
            ot      = api.get_all_open_time()
            tipo_op = "digital" if duracion >= 5 else "turbo"
            if tipo_op in ot and activo in ot[tipo_op]:
                for exp, info in ot[tipo_op][activo].items():
                    if str(duracion) in str(exp):
                        abierto = info.get("open", False)
                        break
        except:
            pass

        profit_pct = None
        try:
            profits    = api.get_all_profit()
            p_info     = profits.get(activo, {})
            profit_pct = p_info.get("turbo" if duracion <= 5 else "binary")
        except:
            pass

        return jsonify({
            "ok":                  True,
            "activo":              activo,
            "es_otc":              es_otc,
            "intervalo_vela":      f"{intervalo}s",
            "duracion_op":         f"{duracion} min",
            "estrategia_usada":    resultado["estrategia"],
            "volatilidad_mercado": resultado["volatilidad"],
            "senal":               resultado["direccion"],
            "confianza":           f"{resultado['confianza']}%",
            "hora_entrada":        ahora.strftime("%H:%M:%S UTC"),
            "proxima_vela_en":     f"{prox}s",
            "activo_abierto":      abierto,
            "rentabilidad":        f"{round(profit_pct * 100, 1)}%" if profit_pct else "N/D",
            "analisis": {
                "razones":     resultado["razones"],
                "indicadores": resultado["indicadores"],
                "fibonacci":   resultado["fibonacci"],
                "patrones":    resultado["patrones_velas"],
                "score_buy":   resultado["score_buy"],
                "score_sell":  resultado["score_sell"],
            }
        })

    except Exception as e:
        log.exception("Error en /iq/senal")
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  PROFIT / RENTABILIDAD
# ════════════════════════════════════════════════════════════════

@app.route("/iq/profit")
@requiere_conexion
def profit():
    api    = sesion["api"]
    activo = request.args.get("activo", "EURUSD")
    try:
        todos = api.get_all_profit()
        info  = todos.get(activo, {})
        return jsonify({
            "ok":            True,
            "activo":        activo,
            "profit_turbo":  round((info.get("turbo",  0) or 0) * 100, 1),
            "profit_binary": round((info.get("binary", 0) or 0) * 100, 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  TOP ACTIVOS POR RENTABILIDAD
# ════════════════════════════════════════════════════════════════

@app.route("/iq/top_activos")
@requiere_conexion
def top_activos():
    api   = sesion["api"]
    limit = int(request.args.get("limit", 10))
    try:
        profits   = api.get_all_profit()
        open_time = api.get_all_open_time()

        activos_abiertos = set()
        for tipo in ["turbo", "binary", "digital"]:
            if tipo in open_time:
                for activo, datos in open_time[tipo].items():
                    for exp, info in datos.items():
                        if info.get("open"):
                            activos_abiertos.add(activo)

        ranking = []
        for activo, info in profits.items():
            if activo not in activos_abiertos:
                continue
            turbo  = round((info.get("turbo",  0) or 0) * 100, 1)
            binary = round((info.get("binary", 0) or 0) * 100, 1)
            mejor  = max(turbo, binary)
            if mejor > 0:
                ranking.append({
                    "activo":        activo,
                    "es_otc":        "OTC" in activo.upper(),
                    "profit_turbo":  turbo,
                    "profit_binary": binary,
                    "mejor_profit":  mejor,
                })

        ranking.sort(key=lambda x: x["mejor_profit"], reverse=True)

        return jsonify({
            "ok":      True,
            "total":   len(ranking),
            "top":     ranking[:limit],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  DEMO SIN LOGIN
# ════════════════════════════════════════════════════════════════

@app.route("/demo/senal")
def demo_senal():
    import random
    activo     = request.args.get("activo",    "EURUSD")
    intervalo  = int(request.args.get("intervalo",  60))
    duracion   = int(request.args.get("duracion",    1))
    estrategia = request.args.get("estrategia", "auto")

    random.seed(int(time.time()) // intervalo)
    precio = 1.08500
    candles = []
    for i in range(120):
        cambio = random.uniform(-0.0006, 0.0006)
        op = precio
        cl = precio + cambio
        hi = max(op, cl) + random.uniform(0, 0.0004)
        lo = min(op, cl) - random.uniform(0, 0.0004)
        candles.append({"open": op, "close": cl, "max": hi, "min": lo,
                        "ts": int(time.time()) - (120 - i) * intervalo})
        precio = cl

    resultado = generar_senal(candles, estrategia)
    ahora = datetime.now(timezone.utc)
    prox  = intervalo - (int(time.time()) % intervalo)

    return jsonify({
        "ok":                  True,
        "modo":                "DEMO — velas sintéticas",
        "activo":              activo,
        "es_otc":              "OTC" in activo.upper(),
        "intervalo_vela":      f"{intervalo}s",
        "duracion_op":         f"{duracion} min",
        "estrategia_usada":    resultado.get("estrategia", estrategia),
        "volatilidad_mercado": resultado.get("volatilidad", "media"),
        "senal":               resultado.get("direccion", "NEUTRAL"),
        "confianza":           f"{resultado.get('confianza', 50)}%",
        "hora_entrada":        ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en":     f"{prox}s",
        "rentabilidad_estimada": "82%",
        "analisis": {k: v for k, v in resultado.items()
                     if k not in ("direccion", "confianza")}
    })


# ════════════════════════════════════════════════════════════════
#  ARRANQUE
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("=" * 60)
    print("  IQ Option Bot API  v6.0")
    print(f"  http://0.0.0.0:{port}")
    print("  Acceso: solo email + password de IQ Option")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
