"""
server.py — IQ Option Bot API v2.1
Corregido para estructura flat (archivos sueltos en Railway)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util

from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import logging
import threading
from datetime import datetime, timezone
from functools import wraps

from analysis import generar_senal, detectar_volatilidad, seleccionar_estrategia_auto

API_KEY = os.environ.get("API_KEY", "l2nHjjc2pS5I0VuLjaJmquPNsR87Sa1glQqJmjRNHWE")
PORT    = int(os.environ.get("PORT", 8000))

app = Flask(__name__)
CORS(app, origins="*")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

sesion = {"api": None, "email": None, "conectado": False, "lock": threading.Lock()}

def requiere_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        key = (request.headers.get("X-API-Key")
               or request.args.get("api_key")
               or (request.get_json(silent=True) or {}).get("api_key"))
        if key != API_KEY:
            return jsonify({"error": "API key invalida"}), 401
        return f(*args, **kwargs)
    return wrapper

def requiere_conexion(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not sesion["conectado"] or sesion["api"] is None:
            return jsonify({"error": "No conectado. Llama primero POST /iq/conectar"}), 403
        return f(*args, **kwargs)
    return wrapper

def raw_a_vela(c):
    return {
        "timestamp": c["from"],
        "datetime": datetime.fromtimestamp(c["from"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "open": c["open"], "high": c["max"], "low": c["min"], "close": c["close"],
        "max": c["max"], "min": c["min"],
    }

@app.route("/")
def raiz():
    return jsonify({
        "api": "IQ Option Bot API", "version": "2.1", "estado": "online",
        "tu_api_key": API_KEY,
        "endpoints": [
            "POST /iq/conectar",
            "GET  /iq/estado",
            "GET  /iq/activos",
            "GET  /iq/velas",
            "POST /iq/senal",
            "GET  /iq/profit",
            "GET  /demo/senal",
        ]
    })

@app.route("/demo/senal")
@requiere_key
def demo_senal():
    import random
    activo     = request.args.get("activo", "EURUSD")
    intervalo  = int(request.args.get("intervalo", 60))
    duracion   = int(request.args.get("duracion", 1))
    estrategia = request.args.get("estrategia", "auto")
    random.seed(int(time.time()) // intervalo)
    precio = 1.08500
    candles = []
    for i in range(120):
        cambio = random.uniform(-0.0006, 0.0006)
        op = precio; cl = precio + cambio
        hi = max(op, cl) + random.uniform(0, 0.0004)
        lo = min(op, cl) - random.uniform(0, 0.0004)
        candles.append({"open": op, "close": cl, "max": hi, "min": lo})
        precio = cl
    resultado = generar_senal(candles, estrategia)
    ahora = datetime.now(timezone.utc)
    prox = intervalo - (int(time.time()) % intervalo)
    return jsonify({
        "ok": True, "modo": "DEMO",
        "activo": activo, "es_otc": "OTC" in activo.upper(),
        "intervalo_vela": f"{intervalo}s", "duracion_op": f"{duracion} min",
        "estrategia_usada": resultado.get("estrategia", estrategia),
        "volatilidad_mercado": resultado.get("volatilidad", "media"),
        "senal": resultado.get("direccion", "NEUTRAL"),
        "confianza": f"{resultado.get('confianza', 50)}%",
        "hora_entrada": ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en": f"{prox}s",
        "analisis": {k: v for k, v in resultado.items() if k not in ("direccion", "confianza")}
    })

@app.route("/iq/conectar", methods=["POST"])
@requiere_key
def conectar():
    body = request.get_json(force=True)
    email = body.get("email")
    password = body.get("password")
    cuenta = body.get("cuenta", "PRACTICE").upper()
    if not email or not password:
        return jsonify({"error": "Se requieren email y password"}), 400
    try:
        spec = importlib.util.spec_from_file_location(
            "stable_api",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "stable_api.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        IQ_Option = mod.IQ_Option
        with sesion["lock"]:
            if sesion["api"]:
                try: sesion["api"].api.close()
                except: pass
            api = IQ_Option(email, password)
            ok, razon = api.connect()
            if not ok:
                return jsonify({"ok": False, "error": str(razon)}), 401
            api.change_balance(cuenta)
            time.sleep(1)
            saldo = api.get_balance()
            modo = api.get_balance_mode()
            sesion["api"] = api; sesion["email"] = email; sesion["conectado"] = True
        return jsonify({"ok": True, "email": email, "cuenta": modo or cuenta, "saldo": round(saldo, 2) if saldo else None})
    except Exception as e:
        log.exception("Error conectar")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/iq/estado")
@requiere_key
@requiere_conexion
def estado():
    api = sesion["api"]
    try:
        saldo = api.get_balance()
        modo = api.get_balance_mode()
        saldos = {}
        try:
            raw = api.get_balances()
            for b in raw.get("msg", []):
                if b.get("type") == 1: saldos["real"] = round(b["amount"], 2)
                elif b.get("type") == 4: saldos["demo"] = round(b["amount"], 2)
        except: pass
        return jsonify({"conectado": True, "email": sesion["email"],
                        "cuenta_activa": modo, "saldo_activo": round(saldo, 2) if saldo else None,
                        "saldos": saldos})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/iq/desconectar")
@requiere_key
def desconectar():
    with sesion["lock"]:
        if sesion["api"]:
            try: sesion["api"].api.close()
            except: pass
        sesion["api"] = None; sesion["conectado"] = False; sesion["email"] = None
    return jsonify({"ok": True})

@app.route("/iq/activos")
@requiere_key
@requiere_conexion
def activos():
    api = sesion["api"]
    solo_ab = request.args.get("solo_abiertos", "0") == "1"
    tipo = request.args.get("tipo", "all")
    try:
        open_time = api.get_all_open_time()
        tipos_map = {"binary": ["turbo","binary"], "digital": ["digital"], "all": ["turbo","binary","digital"]}
        resultado = {}
        for t in tipos_map.get(tipo, tipos_map["all"]):
            if t not in open_time: continue
            for activo, datos in open_time[t].items():
                es_otc = "OTC" in activo.upper()
                for exp, info in datos.items():
                    abierto = info.get("open", False)
                    if solo_ab and not abierto: continue
                    if activo not in resultado:
                        resultado[activo] = {"es_otc": es_otc, "tipos": {}}
                    resultado[activo]["tipos"][f"{t}_{exp}"] = {"abierto": abierto}
        return jsonify({"ok": True, "total": len(resultado), "activos": resultado})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/iq/velas")
@requiere_key
@requiere_conexion
def velas():
    api = sesion["api"]
    activo = request.args.get("activo", "EURUSD")
    intervalo = int(request.args.get("intervalo", 60))
    cantidad = int(request.args.get("cantidad", 100))
    try:
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if raw is None:
            return jsonify({"error": f"Sin datos para {activo}"}), 404
        return jsonify({"ok": True, "activo": activo, "intervalo": f"{intervalo}s",
                        "cantidad": len(raw), "velas": [raw_a_vela(c) for c in raw]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/iq/senal", methods=["POST"])
@requiere_key
@requiere_conexion
def senal():
    api = sesion["api"]
    body = request.get_json(force=True)
    activo = body.get("activo", "EURUSD")
    intervalo = int(body.get("intervalo", 60))
    duracion = int(body.get("duracion", 1))
    cantidad = int(body.get("cantidad_velas", 100))
    estrategia = body.get("estrategia", "auto")
    try:
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if raw is None:
            return jsonify({"error": f"Sin velas para {activo}"}), 404
        candles = [raw_a_vela(c) for c in raw]
        resultado = generar_senal(candles, estrategia)
        if "error" in resultado:
            return jsonify(resultado), 400
        ahora = datetime.now(timezone.utc)
        prox = intervalo - (int(time.time()) % intervalo)
        profit_pct = None
        try:
            profits = api.get_all_profit()
            p_info = profits.get(activo, {})
            profit_pct = p_info.get("turbo" if duracion <= 5 else "binary")
        except: pass
        return jsonify({
            "ok": True, "activo": activo, "es_otc": "OTC" in activo.upper(),
            "intervalo_vela": f"{intervalo}s", "duracion_op": f"{duracion} min",
            "estrategia_usada": resultado["estrategia"],
            "volatilidad_mercado": resultado["volatilidad"],
            "senal": resultado["direccion"], "confianza": f"{resultado['confianza']}%",
            "hora_entrada": ahora.strftime("%H:%M:%S UTC"),
            "proxima_vela_en": f"{prox}s",
            "rentabilidad": f"{round(profit_pct*100,1)}%" if profit_pct else "N/D",
            "analisis": {
                "razones": resultado["razones"], "indicadores": resultado["indicadores"],
                "fibonacci": resultado["fibonacci"], "patrones": resultado["patrones_velas"],
                "score_buy": resultado["score_buy"], "score_sell": resultado["score_sell"],
            }
        })
    except Exception as e:
        log.exception("Error senal")
        return jsonify({"error": str(e)}), 500

@app.route("/iq/profit")
@requiere_key
@requiere_conexion
def profit():
    api = sesion["api"]
    activo = request.args.get("activo", "EURUSD")
    try:
        todos = api.get_all_profit()
        info = todos.get(activo, {})
        return jsonify({"ok": True, "activo": activo,
                        "profit_turbo": round((info.get("turbo",0) or 0)*100,1),
                        "profit_binary": round((info.get("binary",0) or 0)*100,1)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print(f"IQ Option Bot API — puerto {PORT}")
    print(f"API Key: {API_KEY}")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
