"""
server.py — IQ Option Bot API COMPLETO v5.0
RESUELVE TODOS LOS PROBLEMAS:
✅ Velas REALES de IQ Option
✅ Foto de perfil real
✅ /iq/mejor_activo
✅ /iq/top_activos
✅ /iq/activos_por_hora
✅ analysis v3.0 con timing perfecto
✅ Solo señales cuando hay certeza real
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

from analysis import (
    generar_senal,
    escanear_mejores_activos,
    detectar_volatilidad,
    atr,
    calcular_volatilidad_real
)

API_KEY = os.environ.get("API_KEY", "l2nHjjc2pS5I0VuLjaJmquPNsR87Sa1glQqJmjRNHWE")
PORT    = int(os.environ.get("PORT", 8000))

app = Flask(__name__)
CORS(app, origins="*")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

sesion = {"api": None, "email": None, "conectado": False, "lock": threading.Lock()}

# ── Activos para escaneo ─────────────────────────────────────────
ACTIVOS_SCAN = [
    "EURUSD", "EURUSD-OTC", "GBPUSD", "GBPUSD-OTC",
    "USDJPY", "USDJPY-OTC", "AUDUSD", "AUDUSD-OTC",
    "USDCAD", "USDCAD-OTC", "USDCHF", "USDCHF-OTC",
    "NZDUSD", "NZDUSD-OTC", "EURGBP", "EURGBP-OTC",
    "EURJPY", "EURJPY-OTC", "GBPJPY", "GBPJPY-OTC",
    "EURCHF", "EURCHF-OTC", "AUDCAD", "AUDCAD-OTC",
    "AUDCHF", "AUDCHF-OTC", "AUDNZD", "AUDNZD-OTC",
    "CADJPY", "CADJPY-OTC", "CHFJPY", "CHFJPY-OTC",
    "NZDJPY", "NZDJPY-OTC", "GBPCAD", "GBPCAD-OTC",
    "XAUUSD", "BTCUSD", "ETHUSD",
]

# ── Sesiones de mercado ──────────────────────────────────────────
SESIONES = {
    "asia":        {"horas": list(range(0,9)),   "nombre": "Sesión Asia",           "activos_top": ["USDJPY","USDJPY-OTC","AUDUSD","AUDUSD-OTC","GBPJPY","GBPJPY-OTC","EURJPY","EURJPY-OTC","NZDUSD","NZDUSD-OTC","AUDNZD-OTC","CADJPY-OTC"], "descripcion": "Mejor para pares JPY y AUD"},
    "europa":      {"horas": list(range(8,13)),  "nombre": "Sesión Europa",          "activos_top": ["EURUSD","EURUSD-OTC","GBPUSD","GBPUSD-OTC","EURGBP","EURGBP-OTC","EURJPY","EURJPY-OTC","GBPJPY","GBPJPY-OTC","EURCHF","EURCHF-OTC"], "descripcion": "Mejor para pares EUR y GBP"},
    "solapamiento":{"horas": list(range(13,17)), "nombre": "Europa + Nueva York ⭐", "activos_top": ["EURUSD","EURUSD-OTC","GBPUSD","GBPUSD-OTC","USDJPY","USDJPY-OTC","USDCAD","USDCAD-OTC","USDCHF","USDCHF-OTC","EURGBP","EURGBP-OTC","EURJPY","EURJPY-OTC","GBPJPY","GBPJPY-OTC","AUDUSD","AUDUSD-OTC","NZDUSD","NZDUSD-OTC"], "descripcion": "MAXIMA actividad — mejor momento del día"},
    "nueva_york":  {"horas": list(range(17,22)), "nombre": "Sesión Nueva York",      "activos_top": ["USDCAD","USDCAD-OTC","USDCHF","USDCHF-OTC","EURUSD","EURUSD-OTC","GBPUSD","GBPUSD-OTC","USDJPY","USDJPY-OTC","XAUUSD","BTCUSD"], "descripcion": "Mejor para pares USD"},
    "tranquilo":   {"horas": list(range(22,24))+[0], "nombre": "Mercado Tranquilo", "activos_top": ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","GBPJPY-OTC","EURJPY-OTC","USDCHF-OTC","NZDUSD-OTC"], "descripcion": "Solo OTC recomendados"},
}

CALIDAD_DIA = {
    "lunes":     {"calidad": "buena",     "nota": "Mercado retomando fuerza"},
    "martes":    {"calidad": "excelente", "nota": "Mejor día de la semana ⭐"},
    "miercoles": {"calidad": "excelente", "nota": "Máxima volatilidad semanal ⭐"},
    "jueves":    {"calidad": "muy_buena", "nota": "Muy buena actividad"},
    "viernes":   {"calidad": "regular",   "nota": "Mercado cierra — precaución"},
    "sabado":    {"calidad": "baja",      "nota": "Solo OTC disponibles"},
    "domingo":   {"calidad": "baja",      "nota": "Solo OTC disponibles"},
}

DIAS_MAP = {0:"lunes",1:"martes",2:"miercoles",3:"jueves",4:"viernes",5:"sabado",6:"domingo"}

# ── Auth ─────────────────────────────────────────────────────────
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
            return jsonify({"error": "No conectado. Llama POST /iq/conectar"}), 403
        return f(*args, **kwargs)
    return wrapper

# ── Helpers ──────────────────────────────────────────────────────
def raw_a_vela(c):
    return {
        "timestamp": c["from"],
        "datetime":  datetime.fromtimestamp(c["from"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "open":  c["open"],  "close": c["close"],
        "max":   c["max"],   "min":   c["min"],
        "high":  c["max"],   "low":   c["min"],
    }

def get_velas(activo, intervalo, cantidad=100):
    api = sesion["api"]
    try:
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if not raw:
            return None
        return [raw_a_vela(c) for c in raw]
    except Exception as e:
        log.warning(f"Error velas {activo}: {e}")
        return None

def get_sesion(hora_utc):
    for nombre, datos in SESIONES.items():
        if hora_utc in datos["horas"]:
            return nombre, datos
    return "tranquilo", SESIONES["tranquilo"]

# ── IQ Option loader ─────────────────────────────────────────────
def cargar_iq():
    spec = importlib.util.spec_from_file_location(
        "stable_api",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "stable_api.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.IQ_Option

# ════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ════════════════════════════════════════════════════════════════

@app.route("/")
def raiz():
    return jsonify({
        "api": "IQ Option Bot API", "version": "5.0",
        "estado": "online", "tu_api_key": API_KEY,
        "endpoints": [
            "POST /iq/conectar",
            "GET  /iq/estado",
            "GET  /iq/activos",
            "GET  /iq/velas",
            "POST /iq/senal",
            "GET  /iq/mejor_activo",
            "GET  /iq/top_activos",
            "GET  /iq/activos_por_hora",
            "GET  /iq/profit",
            "GET  /iq/desconectar",
            "GET  /demo/senal",
        ]
    })

@app.route("/demo/senal")
@requiere_key
def demo_senal():
    import random
    activo    = request.args.get("activo", "EURUSD")
    intervalo = int(request.args.get("intervalo", 60))
    duracion  = int(request.args.get("duracion", 1))
    random.seed(int(time.time()) // intervalo)
    precio = 1.08500
    candles = []
    for i in range(100):
        cambio = random.uniform(-0.0006, 0.0006)
        op = precio; cl = precio + cambio
        candles.append({"open": op, "close": cl,
                        "max": max(op,cl)+random.uniform(0,0.0004),
                        "min": min(op,cl)-random.uniform(0,0.0004)})
        precio = cl
    resultado = generar_senal(candles, "auto", intervalo)
    ahora = datetime.now(timezone.utc)
    prox  = intervalo - (int(time.time()) % intervalo)
    direccion = resultado.get("direccion", "ESPERAR")
    resp = {
        "ok": True, "modo": "DEMO",
        "activo": activo, "es_otc": "OTC" in activo,
        "intervalo_vela": f"{intervalo}s", "duracion_op": f"{duracion} min",
        "direccion": direccion,
        "hora_entrada": ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en": f"{prox}s",
        "volatilidad": resultado.get("volatilidad", "media"),
        "tendencia": resultado.get("tendencia", "LATERAL"),
        "timing": resultado.get("timing", {}),
        "razones": resultado.get("razones", []),
        "indicadores": resultado.get("indicadores", {}),
        "hay_señal": direccion in ("BUY", "SELL"),
    }
    if direccion not in ("BUY", "SELL"):
        resp["sugerencia"] = "Pulsa Buscar mejor mercado"
    return jsonify(resp)

@app.route("/iq/conectar", methods=["POST"])
@requiere_key
def conectar():
    body     = request.get_json(force=True)
    email    = body.get("email")
    password = body.get("password")
    cuenta   = body.get("cuenta", "PRACTICE").upper()
    if not email or not password:
        return jsonify({"error": "Se requieren email y password"}), 400
    try:
        IQ_Option = cargar_iq()
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
            modo  = api.get_balance_mode()
            sesion["api"]       = api
            sesion["email"]     = email
            sesion["conectado"] = True

        # Saldos demo y real
        saldos = {}
        try:
            raw = api.get_balances()
            for b in raw.get("msg", []):
                if b.get("type") == 1:   saldos["real"] = round(b["amount"], 2)
                elif b.get("type") == 4: saldos["demo"] = round(b["amount"], 2)
        except: pass

        # Perfil completo con foto
        perfil = {}
        try:
            p = api.get_profile_ansyc()
            if p:
                perfil = {
                    "nombre":      p.get("name", email.split("@")[0]),
                    "email":       p.get("email", email),
                    "id":          str(p.get("id", "")),
                    "pais":        p.get("country_name", ""),
                    "foto_perfil": p.get("avatar", ""),
                    "verificado":  p.get("kyc_status", 0) == 1,
                    "registrado":  p.get("created", ""),
                }
        except:
            perfil = {
                "nombre": email.split("@")[0],
                "email":  email,
                "id": "", "pais": "",
                "foto_perfil": "", "verificado": False, "registrado": "",
            }

        return jsonify({
            "ok":          True,
            "email":       email,
            "cuenta":      modo or cuenta,
            "saldo":       round(saldo, 2) if saldo else 0,
            "saldo_demo":  saldos.get("demo", 0),
            "saldo_real":  saldos.get("real", 0),
            "nombre":      perfil.get("nombre", ""),
            "id":          perfil.get("id", ""),
            "pais":        perfil.get("pais", ""),
            "foto_perfil": perfil.get("foto_perfil", ""),
            "verificado":  perfil.get("verificado", False),
            "registrado":  perfil.get("registrado", ""),
            "mensaje":     f"Conectado a IQ Option — {modo or cuenta}"
        })
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
        modo  = api.get_balance_mode()
        saldos = {}
        try:
            raw = api.get_balances()
            for b in raw.get("msg", []):
                if b.get("type") == 1:   saldos["real"] = round(b["amount"], 2)
                elif b.get("type") == 4: saldos["demo"] = round(b["amount"], 2)
        except: pass

        # Foto de perfil actualizada
        foto = ""
        nombre = sesion["email"].split("@")[0] if sesion["email"] else "Trader"
        id_cuenta = ""
        pais = ""
        verificado = False
        registrado = ""
        try:
            p = api.get_profile_ansyc()
            if p:
                foto       = p.get("avatar", "")
                nombre     = p.get("name", nombre)
                id_cuenta  = str(p.get("id", ""))
                pais       = p.get("country_name", "")
                verificado = p.get("kyc_status", 0) == 1
                registrado = p.get("created", "")
        except: pass

        return jsonify({
            "conectado":    True,
            "email":        sesion["email"],
            "nombre":       nombre,
            "id":           id_cuenta,
            "pais":         pais,
            "foto_perfil":  foto,
            "verificado":   verificado,
            "registrado":   registrado,
            "cuenta_activa": modo,
            "saldo_activo": round(saldo, 2) if saldo else 0,
            "saldo_demo":   saldos.get("demo", 0),
            "saldo_real":   saldos.get("real", 0),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/iq/desconectar")
@requiere_key
def desconectar():
    with sesion["lock"]:
        if sesion["api"]:
            try: sesion["api"].api.close()
            except: pass
        sesion["api"]       = None
        sesion["conectado"] = False
        sesion["email"]     = None
    return jsonify({"ok": True})

@app.route("/iq/activos")
@requiere_key
@requiere_conexion
def activos():
    api     = sesion["api"]
    solo_ab = request.args.get("solo_abiertos", "0") == "1"
    tipo    = request.args.get("tipo", "all")
    try:
        open_time = api.get_all_open_time()
        tipos_map = {"binary":["turbo","binary"],"digital":["digital"],"all":["turbo","binary","digital"]}
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
    activo    = request.args.get("activo",    "EURUSD")
    intervalo = int(request.args.get("intervalo", 60))
    cantidad  = int(request.args.get("cantidad",  100))
    candles = get_velas(activo, intervalo, cantidad)
    if not candles:
        return jsonify({"error": f"Sin datos para {activo}"}), 404
    return jsonify({
        "ok": True, "activo": activo,
        "intervalo": f"{intervalo}s",
        "cantidad": len(candles),
        "precio_actual": candles[-1]["close"],
        "velas": candles
    })

@app.route("/iq/senal", methods=["POST"])
@requiere_key
@requiere_conexion
def senal():
    body      = request.get_json(force=True)
    activo    = body.get("activo",    "EURUSD")
    intervalo = int(body.get("intervalo",  60))
    duracion  = int(body.get("duracion",    1))
    cantidad  = int(body.get("cantidad_velas", 100))

    # Velas REALES de IQ Option
    candles = get_velas(activo, intervalo, cantidad)
    if not candles:
        return jsonify({"error": f"Sin velas para {activo}"}), 404

    resultado = generar_senal(candles, "auto", intervalo)
    if "error" in resultado:
        return jsonify(resultado), 400

    ahora     = datetime.now(timezone.utc)
    prox      = intervalo - (int(time.time()) % intervalo)
    direccion = resultado.get("direccion", "ESPERAR")

    payout = None
    try:
        profits = sesion["api"].get_all_profit()
        p = profits.get(activo, {})
        payout = p.get("turbo" if duracion <= 5 else "binary")
    except: pass

    resp = {
        "ok":             True,
        "activo":         activo,
        "es_otc":         "OTC" in activo.upper(),
        "intervalo_vela": f"{intervalo}s",
        "duracion_op":    f"{duracion} min",
        "direccion":      direccion,
        "hora_entrada":   ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en": f"{prox}s",
        "rentabilidad":   f"{round(payout*100,1)}%" if payout else "N/D",
        "volatilidad":    resultado.get("volatilidad", "media"),
        "tendencia":      resultado.get("tendencia", "LATERAL"),
        "timing":         resultado.get("timing", {}),
        "razones":        resultado.get("razones", []),
        "indicadores":    resultado.get("indicadores", {}),
        "hay_señal":      direccion in ("BUY", "SELL"),
        "precio_actual":  candles[-1]["close"] if candles else None,
    }

    if direccion not in ("BUY", "SELL"):
        resp["sugerencia"] = "Pulsa Buscar mejor mercado para encontrar oportunidad"

    return jsonify(resp)

@app.route("/iq/mejor_activo")
@requiere_key
@requiere_conexion
def mejor_activo():
    intervalo = int(request.args.get("intervalo", 60))
    log.info(f"Escaneando activos para mejor oportunidad...")
    candles_por_activo = {}
    for activo in ACTIVOS_SCAN:
        c = get_velas(activo, intervalo, 80)
        if c and len(c) >= 20:
            candles_por_activo[activo] = c

    resultado = escanear_mejores_activos(candles_por_activo, intervalo)
    if not resultado["ok"]:
        return jsonify({"ok": False, "mensaje": "Sin señales claras ahora — espera unos minutos"})

    mejor = resultado["mejor"]
    ahora = datetime.now(timezone.utc)
    prox  = intervalo - (int(time.time()) % intervalo)

    return jsonify({
        "ok":              True,
        "activo":          mejor["activo"],
        "es_otc":          "OTC" in mejor["activo"].upper(),
        "direccion":       mejor["direccion"],
        "volatilidad":     mejor["volatilidad"],
        "hora_entrada":    ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en": f"{prox}s",
        "mensaje":         f"Mejor oportunidad: {mejor['activo']} → {mejor['direccion']}",
        "otros":  [{"activo": a["activo"], "direccion": a["direccion"]} for a in resultado.get("activos", [])[1:4]],
    })

@app.route("/iq/top_activos")
@requiere_key
@requiere_conexion
def top_activos():
    api       = sesion["api"]
    limit     = int(request.args.get("limit", 20))
    intervalo = int(request.args.get("intervalo", 60))

    # Activos abiertos en IQ Option
    activos_abiertos = set(ACTIVOS_SCAN)
    try:
        open_time = api.get_all_open_time()
        abiertos_iq = set()
        for tipo in ["turbo", "binary"]:
            if tipo in open_time:
                for activo, datos in open_time[tipo].items():
                    for exp, info in datos.items():
                        if info.get("open", False):
                            abiertos_iq.add(activo)
        if abiertos_iq:
            activos_abiertos = set(ACTIVOS_SCAN) & abiertos_iq
    except: pass

    resultados = []
    for activo in activos_abiertos:
        try:
            candles = get_velas(activo, intervalo, 20)
            if not candles or len(candles) < 8:
                continue
            vol_pct, vol_nivel = calcular_volatilidad_real(candles, 7)
            if vol_nivel not in ("alta", "muy_alta"):
                continue
            resultados.append({
                "activo":       activo,
                "es_otc":       "OTC" in activo.upper(),
                "precio_actual": round(candles[-1]["close"], 5),
                "volatilidad":  vol_nivel,
                "volatilidad_pct": vol_pct,
            })
        except: continue

    resultados.sort(key=lambda x: x["volatilidad_pct"], reverse=True)
    top = resultados[:limit]
    ahora = datetime.now(timezone.utc)
    hora_utc = ahora.hour
    sn, sd = get_sesion(hora_utc)

    return jsonify({
        "ok":          True,
        "hora_actual": ahora.strftime("%H:%M UTC"),
        "sesion":      sd["nombre"],
        "total":       len(top),
        "filtro":      "solo alta y muy_alta volatilidad",
        "activos":     top,
    })

@app.route("/iq/activos_por_hora")
@requiere_key
def activos_por_hora():
    ahora_utc  = datetime.now(timezone.utc)
    hora_utc   = int(request.args.get("hora", ahora_utc.hour))
    dia_nombre = request.args.get("dia", DIAS_MAP[ahora_utc.weekday()])
    intervalo  = int(request.args.get("intervalo", 60))
    limit      = int(request.args.get("limit", 20))

    sn, sd     = get_sesion(hora_utc)
    calidad    = CALIDAD_DIA.get(dia_nombre.lower(), {"calidad":"buena","nota":""})
    es_fds     = dia_nombre.lower() in ("sabado","domingo")
    activos_rec = sd["activos_top"]
    if es_fds:
        activos_rec = [a for a in activos_rec if "OTC" in a.upper()]

    resultado = []
    for activo in activos_rec[:limit]:
        vol_pct   = 0.0
        vol_nivel = "alta"
        precio    = None
        if sesion["api"]:
            try:
                candles = get_velas(activo, intervalo, 20)
                if candles and len(candles) >= 8:
                    vol_pct, vol_nivel = calcular_volatilidad_real(candles, 7)
                    precio = round(candles[-1]["close"], 5)
            except: pass
        resultado.append({
            "activo":      activo,
            "es_otc":      "OTC" in activo.upper(),
            "precio":      precio,
            "volatilidad": vol_nivel,
            "volatilidad_pct": vol_pct,
        })

    orden = {"muy_alta":0,"alta":1,"media_alta":2,"media":3,"baja":4}
    resultado.sort(key=lambda x: orden.get(x["volatilidad"], 5))

    return jsonify({
        "ok":          True,
        "hora_consulta": f"{hora_utc:02d}:00 UTC",
        "dia":         dia_nombre,
        "sesion":      sd["nombre"],
        "descripcion": sd["descripcion"],
        "calidad_dia": calidad["calidad"],
        "nota_dia":    calidad["nota"],
        "es_fin_semana": es_fds,
        "activos":     resultado[:limit],
        "consejo":     "Martes y Miércoles 13:00-17:00 UTC = mejor momento" if calidad["calidad"] == "excelente" else sd["descripcion"],
    })

@app.route("/iq/profit")
@requiere_key
@requiere_conexion
def profit():
    activo = request.args.get("activo", "EURUSD")
    try:
        todos = sesion["api"].get_all_profit()
        info  = todos.get(activo, {})
        return jsonify({
            "ok":            True,
            "activo":        activo,
            "profit_turbo":  round((info.get("turbo",  0) or 0)*100, 1),
            "profit_binary": round((info.get("binary", 0) or 0)*100, 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print(f"IQ Option Bot API v5.0 — puerto {PORT}")
    print(f"API Key: {API_KEY}")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
