"""
server.py — IQ Option Bot API FINAL
- Sin seleccion manual de estrategia
- Python decide todo automaticamente
- Endpoint /mejor_activo para cuando no hay señal
- Solo genera señal cuando hay certeza real 90%+
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

from analysis_final import generar_senal, escanear_mejores_activos, detectar_volatilidad, atr

API_KEY = os.environ.get("API_KEY", "l2nHjjc2pS5I0VuLjaJmquPNsR87Sa1glQqJmjRNHWE")
PORT    = int(os.environ.get("PORT", 8000))

app = Flask(__name__)
CORS(app, origins="*")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

sesion = {"api": None, "email": None, "conectado": False, "lock": threading.Lock()}

# Lista de activos para escaneo automatico
ACTIVOS_SCAN = [
    "EURUSD", "EURUSD-OTC", "GBPUSD", "GBPUSD-OTC",
    "USDJPY", "USDJPY-OTC", "AUDUSD", "AUDUSD-OTC",
    "USDCAD", "USDCAD-OTC", "EURGBP", "EURGBP-OTC",
    "EURJPY", "EURJPY-OTC", "GBPJPY", "GBPJPY-OTC",
    "USDCHF", "USDCHF-OTC", "NZDUSD", "NZDUSD-OTC",
]

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
        "open": c["open"], "close": c["close"],
        "max": c["max"], "min": c["min"],
        "high": c["max"], "low": c["min"],
    }

def obtener_velas_activo(activo, intervalo, cantidad=100):
    """Obtiene velas de un activo via IQ Option API"""
    api = sesion["api"]
    try:
        raw = api.get_candles(activo, intervalo, cantidad, time.time())
        if not raw:
            return None
        return [raw_a_vela(c) for c in raw]
    except Exception as e:
        log.warning(f"Error velas {activo}: {e}")
        return None

@app.route("/")
def raiz():
    return jsonify({
        "api": "IQ Option Bot API FINAL", "version": "3.0",
        "estado": "online", "tu_api_key": API_KEY,
        "filosofia": "Python decide todo — sin estrategia manual",
        "endpoints": [
            "POST /iq/conectar   { email, password, cuenta }",
            "GET  /iq/estado",
            "GET  /iq/activos",
            "GET  /iq/velas?activo=EURUSD&intervalo=60",
            "POST /iq/senal      { activo, intervalo, duracion }",
            "GET  /iq/mejor_activo?intervalo=60",
            "GET  /iq/desconectar",
            "GET  /demo/senal?activo=EURUSD&intervalo=60",
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
        candles.append({
            "open": op, "close": cl,
            "max": max(op,cl)+random.uniform(0,0.0004),
            "min": min(op,cl)-random.uniform(0,0.0004)
        })
        precio = cl

    resultado = generar_senal(candles, "auto", intervalo)
    ahora = datetime.now(timezone.utc)
    prox  = intervalo - (int(time.time()) % intervalo)
    direccion = resultado.get("direccion", "ESPERAR")

    respuesta = {
        "ok": True, "modo": "DEMO",
        "activo": activo, "es_otc": "OTC" in activo,
        "intervalo_vela": f"{intervalo}s",
        "duracion_op": f"{duracion} min",
        "direccion": direccion,
        "hora_entrada": ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en": f"{prox}s",
        "volatilidad": resultado.get("volatilidad", "media"),
        "tendencia": resultado.get("tendencia", "LATERAL"),
        "razones": resultado.get("razones", []),
        "indicadores": resultado.get("indicadores", {}),
        "hay_señal": direccion in ("BUY", "SELL"),
    }

    if direccion == "ESPERAR":
        respuesta["mensaje"] = "Sin oportunidad clara en este activo ahora"
        respuesta["sugerencia"] = "Pulsa 'Buscar mejor mercado' para encontrar oportunidades"

    return jsonify(respuesta)

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
            modo  = api.get_balance_mode()
            sesion["api"] = api
            sesion["email"] = email
            sesion["conectado"] = True
        # Obtener saldos demo y real
        saldos = {}
        try:
            raw = api.get_balances()
            for b in raw.get("msg", []):
                if b.get("type") == 1: saldos["real"] = round(b["amount"], 2)
                elif b.get("type") == 4: saldos["demo"] = round(b["amount"], 2)
        except: pass
        return jsonify({
            "ok": True, "email": email,
            "cuenta": modo or cuenta,
            "saldo": round(saldo, 2) if saldo else None,
            "saldo_demo": saldos.get("demo", 0),
            "saldo_real": saldos.get("real", 0),
            "mensaje": f"Conectado a IQ Option — {modo or cuenta}"
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
                if b.get("type") == 1: saldos["real"] = round(b["amount"], 2)
                elif b.get("type") == 4: saldos["demo"] = round(b["amount"], 2)
        except: pass
        return jsonify({
            "conectado": True, "email": sesion["email"],
            "cuenta_activa": modo,
            "saldo_activo": round(saldo, 2) if saldo else None,
            "saldos": saldos,
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
        sesion["api"] = None
        sesion["conectado"] = False
        sesion["email"] = None
    return jsonify({"ok": True})

@app.route("/iq/activos")
@requiere_key
@requiere_conexion
def activos():
    api = sesion["api"]
    solo_ab = request.args.get("solo_abiertos", "0") == "1"
    tipo    = request.args.get("tipo", "all")
    try:
        open_time = api.get_all_open_time()
        tipos_map = {
            "binary":  ["turbo","binary"],
            "digital": ["digital"],
            "all":     ["turbo","binary","digital"]
        }
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
    activo    = request.args.get("activo", "EURUSD")
    intervalo = int(request.args.get("intervalo", 60))
    cantidad  = int(request.args.get("cantidad", 100))
    candles = obtener_velas_activo(activo, intervalo, cantidad)
    if not candles:
        return jsonify({"error": f"Sin datos para {activo}"}), 404
    return jsonify({
        "ok": True, "activo": activo,
        "intervalo": f"{intervalo}s",
        "cantidad": len(candles),
        "velas": candles
    })

@app.route("/iq/senal", methods=["POST"])
@requiere_key
@requiere_conexion
def senal():
    """
    Genera señal para el activo seleccionado.
    Python decide la estrategia automaticamente.
    Si no hay señal → indica que use /iq/mejor_activo
    """
    body      = request.get_json(force=True)
    activo    = body.get("activo", "EURUSD")
    intervalo = int(body.get("intervalo", 60))
    duracion  = int(body.get("duracion", 1))
    cantidad  = int(body.get("cantidad_velas", 100))

    candles = obtener_velas_activo(activo, intervalo, cantidad)
    if not candles:
        return jsonify({"error": f"Sin velas para {activo}"}), 404

    resultado = generar_senal(candles, "auto", intervalo)
    if "error" in resultado:
        return jsonify(resultado), 400

    ahora     = datetime.now(timezone.utc)
    prox      = intervalo - (int(time.time()) % intervalo)
    es_otc    = "OTC" in activo.upper()
    direccion = resultado.get("direccion", "ESPERAR")

    # Obtener payout
    payout = None
    try:
        profits = sesion["api"].get_all_profit()
        p = profits.get(activo, {})
        payout = p.get("turbo" if duracion <= 5 else "binary")
    except: pass

    respuesta = {
        "ok":             True,
        "activo":         activo,
        "es_otc":         es_otc,
        "intervalo_vela": f"{intervalo}s",
        "duracion_op":    f"{duracion} min",
        "direccion":      direccion,
        "hora_entrada":   ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en": f"{prox}s",
        "rentabilidad":   f"{round(payout*100,1)}%" if payout else "N/D",
        "volatilidad":    resultado.get("volatilidad", "media"),
        "tendencia":      resultado.get("tendencia", "LATERAL"),
        "razones":        resultado.get("razones", []),
        "indicadores":    resultado.get("indicadores", {}),
        "hay_señal":      direccion in ("BUY", "SELL"),
    }

    if direccion == "ESPERAR":
        respuesta["mensaje"]    = "Sin oportunidad clara en este activo ahora"
        respuesta["sugerencia"] = "Pulsa 'Buscar mejor mercado' para encontrar la mejor oportunidad"

    return jsonify(respuesta)


@app.route("/iq/mejor_activo")
@requiere_key
@requiere_conexion
def mejor_activo():
    """
    Escanea todos los activos y devuelve el mejor del momento.
    Se activa cuando el usuario pulsa 'Buscar mejor mercado'.
    """
    intervalo = int(request.args.get("intervalo", 60))
    cantidad  = int(request.args.get("cantidad", 80))

    log.info(f"Escaneando {len(ACTIVOS_SCAN)} activos para intervalo {intervalo}s...")

    candles_por_activo = {}
    for activo in ACTIVOS_SCAN:
        candles = obtener_velas_activo(activo, intervalo, cantidad)
        if candles and len(candles) >= 20:
            candles_por_activo[activo] = candles

    if not candles_por_activo:
        return jsonify({
            "ok": False,
            "mensaje": "No se pudieron obtener datos de mercado"
        }), 500

    resultado = escanear_mejores_activos(candles_por_activo, intervalo)

    if not resultado["ok"]:
        return jsonify({
            "ok":      False,
            "mensaje": "Mercado tranquilo — ningún activo tiene señal fuerte ahora",
            "consejo": "Espera unos minutos y vuelve a intentar",
        })

    mejor = resultado["mejor"]
    ahora = datetime.now(timezone.utc)
    prox  = intervalo - (int(time.time()) % intervalo)

    return jsonify({
        "ok":             True,
        "activo":         mejor["activo"],
        "es_otc":         "OTC" in mejor["activo"].upper(),
        "direccion":      mejor["direccion"],
        "volatilidad":    mejor["volatilidad"],
        "hora_entrada":   ahora.strftime("%H:%M:%S UTC"),
        "proxima_vela_en": f"{prox}s",
        "mensaje":        f"Mejor oportunidad ahora: {mejor['activo']} → {mejor['direccion']}",
        "otros_activos":  [
            {
                "activo":    a["activo"],
                "direccion": a["direccion"],
                "volatilidad": a["volatilidad"],
            }
            for a in resultado.get("activos", [])[1:4]
        ],
        "analisis": mejor.get("analisis", {}),
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
            "ok": True, "activo": activo,
            "profit_turbo":  round((info.get("turbo", 0) or 0)*100, 1),
            "profit_binary": round((info.get("binary", 0) or 0)*100, 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Agregar este endpoint al server.py de IQ Option ──────────────

# Lista completa de activos a escanear
ACTIVOS_COMPLETOS = [
    # Forex principales
    "EURUSD", "EURUSD-OTC", "GBPUSD", "GBPUSD-OTC",
    "USDJPY", "USDJPY-OTC", "AUDUSD", "AUDUSD-OTC",
    "USDCAD", "USDCAD-OTC", "USDCHF", "USDCHF-OTC",
    "NZDUSD", "NZDUSD-OTC", "EURGBP", "EURGBP-OTC",
    "EURJPY", "EURJPY-OTC", "GBPJPY", "GBPJPY-OTC",
    "EURCHF", "EURCHF-OTC", "AUDCAD", "AUDCAD-OTC",
    "AUDCHF", "AUDCHF-OTC", "AUDNZD", "AUDNZD-OTC",
    "CADJPY", "CADJPY-OTC", "CHFJPY", "CHFJPY-OTC",
    "NZDJPY", "NZDJPY-OTC", "GBPCAD", "GBPCAD-OTC",
    "GBPCHF", "GBPCHF-OTC", "EURCAD", "EURCAD-OTC",
    "EURAUD", "EURAUD-OTC", "EURNZD", "EURNZD-OTC",
    # Crypto
    "BTCUSD", "ETHUSD", "LTCUSD",
    # Materias primas
    "XAUUSD", "XAGUSD",
]

def calcular_volatilidad_real(candles, periodo=14):
    """
    Calcula ATR% real — la verdadera volatilidad del activo.
    Retorna porcentaje de movimiento promedio por vela.
    """
    if len(candles) < periodo + 1:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h  = candles[i]["max"]
        l  = candles[i]["min"]
        pc = candles[i-1]["close"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    atr_val = sum(trs[-periodo:]) / periodo
    precio  = candles[-1]["close"]
    if precio == 0:
        return 0.0
    return round((atr_val / precio) * 100, 4)


@app.route("/iq/top_activos")
@requiere_key
@requiere_conexion
def top_activos():
    """
    Devuelve los activos con MAYOR volatilidad real del momento.
    Solo muestra activos con volatilidad ALTA (ATR% > 0.15%).
    Se activa cuando el usuario selecciona una hora.

    Parametros:
      limit    → cuantos activos devolver (default 20)
      intervalo → segundos por vela (default 60)
    """
    api      = sesion["api"]
    limit    = int(request.args.get("limit", 20))
    intervalo = int(request.args.get("intervalo", 60))

    # 1. Obtener activos abiertos en IQ Option
    try:
        open_time = api.get_all_open_time()
        activos_abiertos = set()
        for tipo in ["turbo", "binary"]:
            if tipo in open_time:
                for activo, datos in open_time[tipo].items():
                    for exp, info in datos.items():
                        if info.get("open", False):
                            activos_abiertos.add(activo)
    except Exception as e:
        log.error(f"Error obteniendo activos: {e}")
        activos_abiertos = set(ACTIVOS_COMPLETOS)

    # Filtrar solo los que tenemos en nuestra lista
    activos_a_escanear = [a for a in ACTIVOS_COMPLETOS if a in activos_abiertos]
    if not activos_a_escanear:
        activos_a_escanear = ACTIVOS_COMPLETOS[:30]

    # 2. Calcular volatilidad real de cada activo
    resultados = []
    ahora = datetime.now(timezone.utc)

    for activo in activos_a_escanear:
        try:
            raw = api.get_candles(activo, intervalo, 30, time.time())
            if not raw or len(raw) < 10:
                continue

            candles = [raw_a_vela(c) for c in raw]
            vol_pct = calcular_volatilidad_real(candles, 14)

            # Solo activos con volatilidad ALTA (> 0.15%)
            if vol_pct < 0.15:
                continue

            precio_actual = candles[-1]["close"]
            precio_anterior = candles[-2]["close"] if len(candles) > 1 else precio_actual
            cambio_pct = round(((precio_actual - precio_anterior) / precio_anterior) * 100, 4) if precio_anterior else 0

            # Clasificar nivel de volatilidad
            if vol_pct >= 0.35:
                nivel = "muy_alta"
                barras = "██████████"
            elif vol_pct >= 0.25:
                nivel = "alta"
                barras = "████████"
            else:
                nivel = "alta"
                barras = "██████"

            resultados.append({
                "activo":        activo,
                "es_otc":        "OTC" in activo.upper(),
                "precio_actual": round(precio_actual, 5),
                "cambio_pct":    cambio_pct,
                "volatilidad_pct": vol_pct,
                "nivel_volatilidad": nivel,
                "barras":        barras,
                "ultima_vela": {
                    "open":  candles[-1]["open"],
                    "close": candles[-1]["close"],
                    "high":  candles[-1]["max"],
                    "low":   candles[-1]["min"],
                }
            })

        except Exception as e:
            log.warning(f"Error {activo}: {e}")
            continue

    # 3. Ordenar por volatilidad — los MAS ALTOS primero
    resultados.sort(key=lambda x: x["volatilidad_pct"], reverse=True)

    # 4. Tomar solo los TOP según limit
    top = resultados[:limit]

    if not top:
        return jsonify({
            "ok":      False,
            "mensaje": "No hay activos con alta volatilidad en este momento",
            "consejo": "Intenta en el solapamiento Europa+NY (13:00-17:00 UTC)",
            "hora_actual": ahora.strftime("%H:%M UTC"),
        })

    # 5. Sesion actual
    hora_utc = ahora.hour
    if 0 <= hora_utc < 8:
        sesion_actual = "Asia — USDJPY, AUDUSD, GBPJPY más activos"
    elif 8 <= hora_utc < 13:
        sesion_actual = "Europa — EURUSD, GBPUSD, EURGBP más activos"
    elif 13 <= hora_utc < 17:
        sesion_actual = "Solapamiento Europa+NY — MÁXIMA actividad"
    elif 17 <= hora_utc < 22:
        sesion_actual = "Nueva York — USDCAD, USDCHF, EURUSD más activos"
    else:
        sesion_actual = "Mercado tranquilo — OTC recomendados"

    return jsonify({
        "ok":           True,
        "hora_actual":  ahora.strftime("%H:%M:%S UTC"),
        "sesion":       sesion_actual,
        "total_encontrados": len(resultados),
        "mostrando":    len(top),
        "filtro":       "solo volatilidad ALTA y MUY ALTA",
        "activos":      top,
    })


# ── Agregar este endpoint al server.py de IQ Option ──────────────

# Horarios de sesiones y activos recomendados por hora UTC
SESIONES = {
    "asia": {
        "horas": list(range(0, 9)),  # 00:00 - 08:59 UTC
        "nombre": "Sesión Asia",
        "activos_top": [
            "USDJPY", "USDJPY-OTC", "AUDUSD", "AUDUSD-OTC",
            "GBPJPY", "GBPJPY-OTC", "EURJPY", "EURJPY-OTC",
            "NZDUSD", "NZDUSD-OTC", "AUDJPY", "CADJPY-OTC",
            "CHFJPY", "CHFJPY-OTC", "NZDJPY", "AUDNZD-OTC",
        ],
        "descripcion": "Mejor para pares con JPY y AUD"
    },
    "europa": {
        "horas": list(range(8, 13)),  # 08:00 - 12:59 UTC
        "nombre": "Sesión Europa",
        "activos_top": [
            "EURUSD", "EURUSD-OTC", "GBPUSD", "GBPUSD-OTC",
            "EURGBP", "EURGBP-OTC", "EURJPY", "EURJPY-OTC",
            "GBPJPY", "GBPJPY-OTC", "EURCHF", "EURCHF-OTC",
            "GBPCHF", "GBPCHF-OTC", "EURCAD", "EURCAD-OTC",
        ],
        "descripcion": "Mejor para pares con EUR y GBP"
    },
    "solapamiento": {
        "horas": list(range(13, 17)),  # 13:00 - 16:59 UTC
        "nombre": "Solapamiento Europa + Nueva York",
        "activos_top": [
            "EURUSD", "EURUSD-OTC", "GBPUSD", "GBPUSD-OTC",
            "USDJPY", "USDJPY-OTC", "USDCAD", "USDCAD-OTC",
            "USDCHF", "USDCHF-OTC", "EURGBP", "EURGBP-OTC",
            "EURJPY", "EURJPY-OTC", "GBPJPY", "GBPJPY-OTC",
            "AUDUSD", "AUDUSD-OTC", "NZDUSD", "NZDUSD-OTC",
        ],
        "descripcion": "MAXIMA actividad — todos los activos disponibles"
    },
    "nueva_york": {
        "horas": list(range(17, 22)),  # 17:00 - 21:59 UTC
        "nombre": "Sesión Nueva York",
        "activos_top": [
            "USDCAD", "USDCAD-OTC", "USDCHF", "USDCHF-OTC",
            "EURUSD", "EURUSD-OTC", "GBPUSD", "GBPUSD-OTC",
            "USDJPY", "USDJPY-OTC", "XAUUSD", "BTCUSD",
            "ETHUSD", "AUDCAD", "AUDCAD-OTC", "CADJPY-OTC",
        ],
        "descripcion": "Mejor para pares con USD y materias primas"
    },
    "tranquilo": {
        "horas": list(range(22, 24)) + [0],  # 22:00 - 23:59 UTC
        "nombre": "Mercado Tranquilo",
        "activos_top": [
            "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC",
            "AUDUSD-OTC", "USDCAD-OTC", "EURGBP-OTC",
            "GBPJPY-OTC", "EURJPY-OTC", "USDCHF-OTC",
            "NZDUSD-OTC", "AUDNZD-OTC", "AUDCHF-OTC",
        ],
        "descripcion": "Solo OTC recomendados — mercado con menos liquidez"
    }
}

# Días con mejor rendimiento por sesión
DIAS_RECOMENDADOS = {
    0: "lunes",
    1: "martes",
    2: "miercoles",
    3: "jueves",
    4: "viernes",
    5: "sabado",   # solo OTC
    6: "domingo",  # solo OTC
}

# Mejores días para operar (lunes-jueves son los mejores)
CALIDAD_DIA = {
    "lunes":     {"calidad": "buena",    "nota": "Mercado retomando fuerza"},
    "martes":    {"calidad": "excelente","nota": "Mejor día de la semana"},
    "miercoles": {"calidad": "excelente","nota": "Máxima volatilidad semanal"},
    "jueves":    {"calidad": "muy_buena","nota": "Buena actividad"},
    "viernes":   {"calidad": "regular",  "nota": "Mercado cierra — menor confiabilidad"},
    "sabado":    {"calidad": "baja",     "nota": "Solo OTC disponibles"},
    "domingo":   {"calidad": "baja",     "nota": "Solo OTC disponibles"},
}


def obtener_sesion_actual(hora_utc):
    """Retorna la sesión activa según la hora UTC"""
    for nombre, datos in SESIONES.items():
        if hora_utc in datos["horas"]:
            return nombre, datos
    return "tranquilo", SESIONES["tranquilo"]


@app.route("/iq/activos_por_hora")
@requiere_key
def activos_por_hora():
    """
    Devuelve los activos recomendados para una hora y día específicos.
    Si no se especifica hora/día usa la hora actual.

    Parámetros:
      hora → hora UTC (0-23), default: hora actual
      dia  → nombre del día, default: día actual
      intervalo → segundos por vela, default: 60
      limit → cuántos activos mostrar, default: 20
    """
    from datetime import datetime, timezone

    ahora_utc = datetime.now(timezone.utc)

    # Hora y día (usar actuales si no se especifican)
    hora_utc  = int(request.args.get("hora", ahora_utc.hour))
    dia_nombre = request.args.get("dia", DIAS_RECOMENDADOS[ahora_utc.weekday()])
    intervalo  = int(request.args.get("intervalo", 60))
    limit      = int(request.args.get("limit", 20))

    # Obtener sesión para esa hora
    sesion_nombre, sesion_datos = obtener_sesion_actual(hora_utc)

    # Calidad del día
    calidad_info = CALIDAD_DIA.get(dia_nombre.lower(), {"calidad": "buena", "nota": ""})

    # Si el día es fin de semana → solo OTC
    es_fin_semana = dia_nombre.lower() in ("sabado", "domingo")

    activos_recomendados = sesion_datos["activos_top"]
    if es_fin_semana:
        activos_recomendados = [a for a in activos_recomendados if "OTC" in a.upper()]

    # Si hay API conectada → verificar cuáles están abiertos
    activos_abiertos = set(activos_recomendados)
    if sesion["api"]:
        try:
            open_time = sesion["api"].get_all_open_time()
            activos_iq = set()
            for tipo in ["turbo", "binary"]:
                if tipo in open_time:
                    for activo, datos in open_time[tipo].items():
                        for exp, info in datos.items():
                            if info.get("open", False):
                                activos_iq.add(activo)
            if activos_iq:
                activos_abiertos = set(activos_recomendados) & activos_iq
                if not activos_abiertos:
                    activos_abiertos = set(activos_recomendados)
        except:
            pass

    # Calcular volatilidad real si hay conexión
    resultado_activos = []
    for activo in activos_recomendados:
        if activo not in activos_abiertos:
            continue

        vol_pct   = 0.0
        vol_nivel = "alta"
        precio    = None

        if sesion["api"]:
            try:
                raw = sesion["api"].get_candles(activo, intervalo, 20, time.time())
                if raw and len(raw) >= 5:
                    candles = [raw_a_vela(c) for c in raw]
                    atr_val = atr(candles, 7) if len(candles) >= 8 else None
                    precio  = candles[-1]["close"]
                    if atr_val and precio:
                        vol_pct   = round((atr_val / precio) * 100, 4)
                        if vol_pct >= 0.35: vol_nivel = "muy_alta"
                        elif vol_pct >= 0.25: vol_nivel = "alta"
                        elif vol_pct >= 0.15: vol_nivel = "media_alta"
                        else: vol_nivel = "media"
            except:
                pass

        resultado_activos.append({
            "activo":      activo,
            "es_otc":      "OTC" in activo.upper(),
            "precio":      round(precio, 5) if precio else None,
            "volatilidad": vol_nivel,
            "volatilidad_pct": vol_pct,
            "recomendado": vol_nivel in ("muy_alta", "alta"),
        })

    # Ordenar: primero muy_alta, luego alta, luego el resto
    orden_vol = {"muy_alta": 0, "alta": 1, "media_alta": 2, "media": 3, "baja": 4}
    resultado_activos.sort(key=lambda x: orden_vol.get(x["volatilidad"], 5))

    # Solo los TOP según limit
    top = resultado_activos[:limit]

    # Próximas sesiones
    proximas = []
    for h in range(hora_utc + 1, hora_utc + 25):
        h_real = h % 24
        sn, sd = obtener_sesion_actual(h_real)
        if sn != sesion_nombre:
            proximas.append({
                "hora":   f"{h_real:02d}:00 UTC",
                "sesion": sd["nombre"],
            })
            sesion_nombre = sn
            if len(proximas) >= 3:
                break

    return jsonify({
        "ok":           True,
        "hora_actual":  ahora_utc.strftime("%H:%M UTC"),
        "hora_consulta": f"{hora_utc:02d}:00 UTC",
        "dia":          dia_nombre,
        "sesion":       sesion_datos["nombre"],
        "descripcion":  sesion_datos["descripcion"],
        "calidad_dia":  calidad_info["calidad"],
        "nota_dia":     calidad_info["nota"],
        "es_fin_semana": es_fin_semana,
        "total_activos": len(top),
        "activos":      top,
        "proximas_sesiones": proximas,
        "consejo": (
            "Martes y miércoles 13:00-17:00 UTC = mejor momento de toda la semana"
            if calidad_info["calidad"] == "excelente"
            else f"Sesión actual: {sesion_datos['descripcion']}"
        ),
    })


if __name__ == "__main__":
    print(f"IQ Option Bot API FINAL — puerto {PORT}")
    print(f"API Key: {API_KEY}")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
