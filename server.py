"""
server.py — IQ Option Bot API
Servidor personal protegido con API Key para conectar con Lovable.

SOLO LECTURA — no compra ni vende automáticamente.

Endpoints:
  POST /iq/conectar        → login con email + contraseña
  GET  /iq/estado          → estado de conexión y saldo
  GET  /iq/activos         → lista activos abiertos (OTC y normales)
  GET  /iq/velas           → velas históricas de un activo
  GET  /iq/velas/live      → últimas velas en tiempo real (stream)
  POST /iq/senal           → señal BUY/SELL con análisis técnico
  GET  /iq/profit          → rentabilidad % de un activo
  GET  /iq/desconectar     → cierra la sesión
  GET  /demo/senal         → demo sin login (para probar Lovable)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import time
import json
import logging
import threading
from datetime import datetime, timezone
from functools import wraps

from config import API_KEY, PORT, HOST, IQ_TIMEOUT
from analysis import generar_senal, detectar_volatilidad, seleccionar_estrategia_auto

app = Flask(__name__)
CORS(app, origins="*")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Sesión global IQ ────────────────────────────────────────────
sesion = {"api": None, "email": None, "conectado": False, "lock": threading.Lock()}


# ════════════════════════════════════════════════════════════════
#  Autenticación por API Key
# ════════════════════════════════════════════════════════════════

def requiere_key(f):
    """Decorador: rechaza peticiones sin la API key correcta"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        key = (request.headers.get("X-API-Key")
               or request.args.get("api_key")
               or (request.get_json(silent=True) or {}).get("api_key"))
        if key != API_KEY:
            return jsonify({
                "error": "API key inválida o faltante",
                "hint":  "Incluye el header X-API-Key o el parámetro api_key"
            }), 401
        return f(*args, **kwargs)
    return wrapper


def requiere_conexion(f):
    """Decorador: exige que exista una sesión IQ activa"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not sesion["conectado"] or sesion["api"] is None:
            return jsonify({
                "error": "No hay sesión IQ Option activa",
                "hint":  "Llama primero a POST /iq/conectar"
            }), 403
        return f(*args, **kwargs)
    return wrapper


# ════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════

def esperar(condicion, timeout=IQ_TIMEOUT):
    """Espera activa con timeout para respuestas WebSocket de IQ"""
    ini = time.time()
    while not condicion() and (time.time() - ini) < timeout:
        time.sleep(0.05)
    return condicion()


def raw_a_vela(c):
    return {
        "timestamp": c["from"],
        "datetime":  datetime.fromtimestamp(c["from"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "open":  c["open"],
        "high":  c["max"],
        "low":   c["min"],
        "close": c["close"],
        "volumen": c.get("volume", 0),
        # alias para el motor de análisis
        "max": c["max"],
        "min": c["min"],
    }


# ════════════════════════════════════════════════════════════════
#  Endpoints públicos (no requieren key)
# ════════════════════════════════════════════════════════════════

@app.route("/")
def raiz():
    return jsonify({
        "api":     "IQ Option Bot API",
        "version": "2.0",
        "estado":  "online",
        "uso": {
            "header":    "X-API-Key: <tu_clave>",
            "param_url": "?api_key=<tu_clave>",
        },
        "endpoints": [
            "POST /iq/conectar",
            "GET  /iq/estado",
            "GET  /iq/activos",
            "GET  /iq/velas?activo=EURUSD&intervalo=60&cantidad=100",
            "GET  /iq/velas/live?activo=EURUSD&intervalo=60",
            "POST /iq/senal",
            "GET  /iq/profit?activo=EURUSD",
            "GET  /iq/desconectar",
            "GET  /demo/senal?activo=EURUSD&intervalo=60&estrategia=auto",
        ]
    })


@app.route("/demo/senal")
@requiere_key
def demo_senal():
    """
    Señal de demo con velas sintéticas — no requiere login IQ.
    Útil para probar la integración con Lovable.
    """
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
        op  = precio
        cl  = precio + cambio
        hi  = max(op, cl) + random.uniform(0, 0.0004)
        lo  = min(op, cl) - random.uniform(0, 0.0004)
        candles.append({"open": op, "close": cl, "max": hi, "min": lo,
                        "ts": int(time.time()) - (120 - i) * intervalo})
        precio = cl

    resultado = generar_senal(candles, estrategia)
    ahora = datetime.now(timezone.utc)
    prox = intervalo - (int(time.time()) % intervalo)

    return jsonify({
        "ok":             True,
        "modo":           "DEMO — velas sintéticas",
        "activo":         activo,
        "es_otc":         "OTC" in activo.upper(),
        "intervalo_vela": f"{intervalo}s",
        "duracion_op":    f"{duracion} min",
        "estrategia_usada": resultado.get("estrategia", estrategia),
        "volatilidad_mercado": resultado.get("volatilidad", "media"),
        "senal":          resultado.get("direccion", "NEUTRAL"),
        "confianza":      f"{resultado.get('confianza', 50)}%",
        "hora_entrada":   ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en": f"{prox}s",
        "rentabilidad_estimada": "82%",
        "analisis":       {k: v for k, v in resultado.items()
                           if k not in ("direccion", "confianza")}
    })


# ════════════════════════════════════════════════════════════════
#  Endpoints IQ Option — requieren key + sesión activa
# ════════════════════════════════════════════════════════════════

@app.route("/iq/conectar", methods=["POST"])
@requiere_key
def conectar():
    """
    POST /iq/conectar
    Body JSON: { "email": "...", "password": "...", "cuenta": "PRACTICE" }
    cuenta: "PRACTICE" (demo) o "REAL"
    """
    body     = request.get_json(force=True)
    email    = body.get("email")
    password = body.get("password")
    cuenta   = body.get("cuenta", "PRACTICE").upper()

    if not email or not password:
        return jsonify({"error": "Se requieren email y password"}), 400

    try:
        from iqoptionapi.stable_api import IQ_Option

        with sesion["lock"]:
            # Cerrar sesión anterior si existe
            if sesion["api"]:
                try:
                    sesion["api"].api.close()
                except:
                    pass

            api = IQ_Option(email, password)
            ok, razon = api.connect()

            if not ok:
                return jsonify({"ok": False, "error": str(razon)}), 401

            api.change_balance(cuenta)
            time.sleep(1)

            saldo  = api.get_balance()
            modo   = api.get_balance_mode()

            sesion["api"]       = api
            sesion["email"]     = email
            sesion["conectado"] = True

        return jsonify({
            "ok":      True,
            "email":   email,
            "cuenta":  modo or cuenta,
            "saldo":   round(saldo, 2) if saldo else None,
            "mensaje": f"Conectado a IQ Option — cuenta {modo or cuenta}"
        })

    except Exception as e:
        log.exception("Error en /iq/conectar")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/iq/estado")
@requiere_key
@requiere_conexion
def estado():
    """Devuelve estado de la conexión y saldos de la cuenta"""
    api = sesion["api"]
    try:
        conectado = api.check_connect
        saldo     = api.get_balance() if conectado else None
        modo      = api.get_balance_mode() if conectado else None

        # Obtener ambos saldos (demo y real)
        saldos = {}
        try:
            raw = api.get_balances()
            for b in raw.get("msg", []):
                tipo = b.get("type")
                amt  = b.get("amount", 0)
                if tipo == 1:
                    saldos["real"]  = round(amt, 2)
                elif tipo == 4:
                    saldos["demo"]  = round(amt, 2)
        except:
            pass

        return jsonify({
            "conectado":   conectado,
            "email":       sesion["email"],
            "cuenta_activa": modo,
            "saldo_activo":  round(saldo, 2) if saldo else None,
            "saldos":        saldos,
            "servidor_ts":   api.get_server_timestamp() if conectado else None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/iq/desconectar")
@requiere_key
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


@app.route("/iq/activos")
@requiere_key
@requiere_conexion
def activos():
    """
    GET /iq/activos?tipo=all|binary|digital&solo_abiertos=1
    Retorna activos con estado abierto/cerrado y si son OTC
    """
    api         = sesion["api"]
    tipo        = request.args.get("tipo", "all")
    solo_ab     = request.args.get("solo_abiertos", "0") == "1"

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


@app.route("/iq/velas")
@requiere_key
@requiere_conexion
def velas():
    """
    GET /iq/velas?activo=EURUSD&intervalo=60&cantidad=100
    intervalo en segundos: 60=1min, 300=5min, 3600=1h
    """
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


@app.route("/iq/velas/live")
@requiere_key
@requiere_conexion
def velas_live():
    """
    GET /iq/velas/live?activo=EURUSD&intervalo=60
    Devuelve las últimas 5 velas en tiempo real (suscripción al stream)
    """
    api       = sesion["api"]
    activo    = request.args.get("activo",    "EURUSD")
    intervalo = int(request.args.get("intervalo", 60))

    try:
        api.start_candles_stream(activo, intervalo, 10)
        time.sleep(2)  # esperar datos del stream

        rt = api.get_realtime_candles(activo, intervalo)
        if not rt:
            # fallback a históricas
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


@app.route("/iq/senal", methods=["POST"])
@requiere_key
@requiere_conexion
def senal():
    """
    POST /iq/senal
    Body JSON:
    {
      "activo":         "EURUSD",
      "intervalo":      60,
      "duracion":       1,
      "cantidad_velas": 100,
      "estrategia":     "auto"
    }
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
        # 1. Obtener velas históricas
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if raw is None:
            return jsonify({"error": f"Sin velas para {activo}"}), 404

        candles = [raw_a_vela(c) for c in raw]

        # 2. Análisis técnico
        resultado = generar_senal(candles, estrategia)
        if "error" in resultado:
            return jsonify(resultado), 400

        # 3. Información de mercado
        es_otc = "OTC" in activo.upper()
        ahora  = datetime.now(timezone.utc)
        prox   = intervalo - (int(time.time()) % intervalo)

        # 4. Verificar si está abierto
        abierto = None
        try:
            ot = api.get_all_open_time()
            tipo_op = "digital" if duracion >= 5 else "turbo"
            if tipo_op in ot and activo in ot[tipo_op]:
                for exp, info in ot[tipo_op][activo].items():
                    if str(duracion) in str(exp):
                        abierto = info.get("open", False)
                        break
        except:
            pass

        # 5. Rentabilidad
        profit_pct = None
        try:
            profits = api.get_all_profit()
            p_info  = profits.get(activo, {})
            profit_pct = p_info.get("turbo" if duracion <= 5 else "binary")
        except:
            pass

        return jsonify({
            "ok":              True,
            "activo":          activo,
            "es_otc":          es_otc,
            "intervalo_vela":  f"{intervalo}s",
            "duracion_op":     f"{duracion} min",
            "estrategia_usada": resultado["estrategia"],
            "volatilidad_mercado": resultado["volatilidad"],
            "senal":           resultado["direccion"],
            "confianza":       f"{resultado['confianza']}%",
            "hora_entrada":    ahora.strftime("%H:%M:%S UTC"),
            "proxima_vela_en": f"{prox}s",
            "activo_abierto":  abierto,
            "rentabilidad":    f"{round(profit_pct * 100, 1)}%" if profit_pct else "N/D",
            "analisis": {
                "razones":       resultado["razones"],
                "indicadores":   resultado["indicadores"],
                "fibonacci":     resultado["fibonacci"],
                "patrones":      resultado["patrones_velas"],
                "score_buy":     resultado["score_buy"],
                "score_sell":    resultado["score_sell"],
            }
        })

    except Exception as e:
        log.exception("Error en /iq/senal")
        return jsonify({"error": str(e)}), 500


@app.route("/iq/profit")
@requiere_key
@requiere_conexion
def profit():
    """GET /iq/profit?activo=EURUSD"""
    api    = sesion["api"]
    activo = request.args.get("activo", "EURUSD")
    try:
        todos = api.get_all_profit()
        info  = todos.get(activo, {})
        return jsonify({
            "ok":            True,
            "activo":        activo,
            "profit_turbo":  round((info.get("turbo", 0) or 0) * 100, 1),
            "profit_binary": round((info.get("binary", 0) or 0) * 100, 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  Arranque
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 62)
    print("  🤖  IQ Option Bot API  v2.0")
    print(f"  🌐  http://localhost:{PORT}")
    print("=" * 62)
    print(f"  🔑  Tu API Key para Lovable:")
    print(f"      {API_KEY}")
    print("=" * 62)
    print("  📡  Demo sin login:  GET /demo/senal?activo=EURUSD")
    print("  🔗  Con IQ Option:   POST /iq/conectar → POST /iq/senal")
    print("=" * 62)
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
