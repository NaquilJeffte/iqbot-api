"""
server.py — IQ Option Bot API v12.1
- ESTRUCTURA COMPLETA DE VELAS (color + forma + mechas)
- Escanea TODOS los activos OTC
- Verificación en tiempo real
- Timing PERFECTO en HH:MM:00
- Zona horaria del BROKER (UTC-6)
- Confianza mínima 60%
- Mínimo 1 repetición (SIEMPRE encuentra señales)
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

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
MIN_PATRONES = 1  # ✅ CAMBIADO: 1 repetición es suficiente
VELAS_PARA_ANALISIS = 500
MAX_ACTIVOS_ESCANEAR = 999

# ... (resto del código igual hasta la función senal) ...

@app.route("/iq/senal", methods=["POST"])
@requiere_conexion
def senal():
    """Señal para un activo específico con análisis de estructura completa"""
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
        
        # ✅ CORREGIDO: NO forzamos ESPERAR si analysis.py ya dio BUY/SELL
        # Solo filtramos por confianza mínima
        if resultado["direccion"] in ("BUY", "SELL") and confianza >= CONFIANZA_MINIMA:
            # Señal válida
            pass
        else:
            resultado["direccion"] = "ESPERAR"
            resultado["confianza"] = 0

        # Timing perfecto
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

        profit_pct = None
        try:
            profits = api.get_all_profit()
            profit_pct = profits.get(activo, {}).get("turbo")
        except:
            pass

        es_valida = resultado["direccion"] in ("BUY", "SELL") and confianza >= CONFIANZA_MINIMA

        return jsonify({
            "ok": True,
            "activo": activo,
            "nombre": _nombre_legible(activo),
            "es_otc": "OTC" in activo,
            "senal": resultado["direccion"],
            "confianza": confianza if es_valida else 0,
            "hora_actual": actual_broker.strftime("%H:%M:%S"),
            "hora_entrada": entrada_broker.strftime("%H:%M:%S"),
            "hora_salida": salida_broker.strftime("%H:%M:%S"),
            "hora_verificar": verificar_broker.strftime("%H:%M:%S"),
            "segundos_para_entrar": max(0, round(seg_para_entrar, 1)),
            "timezone": "UTC-6",
            "patrones_encontrados": patrones_encontrados,
            "total_encontrados": resultado.get("total_encontrados", 0),
            "pct_acierto": resultado.get("pct_acierto", 0),
            "cambio_promedio": resultado.get("cambio_promedio", 0),
            "tipo_mas_comun": resultado.get("tipo_mas_comun", "N/A"),
            "fuerza_promedio_siguiente": resultado.get("fuerza_promedio_siguiente", 0),
            "verificacion": resultado.get("verificacion", False),
            "progreso_vela": resultado.get("progreso_vela", 0),
            "fuerza_vela": resultado.get("fuerza_vela", 0),
            "velas_analizadas": resultado.get("velas_analizadas", 0),
            "vela_en_movimiento": resultado.get("vela_en_movimiento", False),
            "razones": resultado.get("razones", []),
            "votos_buy": resultado.get("votos_buy", 0),
            "votos_sell": resultado.get("votos_sell", 0),
            "score_buy": resultado.get("score_buy", 0),
            "score_sell": resultado.get("score_sell", 0),
            "volatilidad": resultado.get("volatilidad", "media"),
            "tendencia": resultado.get("tendencia", "LATERAL"),
            "detalles_estructura": resultado.get("detalles_estructura", []),
            "patron_colores": resultado.get("indicadores", {}).get("patron_colores", ""),
            "patron_tipos": resultado.get("indicadores", {}).get("patron_tipos", ""),
            "duracion_seg": int(duracion_seg),
            "duracion_min": duracion_min,
            "intervalo_vela": intervalo,
            "rentabilidad": f"{round(profit_pct*100,1)}%" if profit_pct else "N/D",
            "indicadores": resultado.get("indicadores", {}),
        })

    except Exception as e:
        log.exception("Error en /iq/senal")
        return jsonify({"error": str(e)}), 500

# ... (resto del código igual, solo cambiar MIN_PATRONES = 1)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("="*80)
    print("  IQ Option Bot API  v12.1 - ESTRUCTURA COMPLETA DE VELAS")
    print(f"  http://0.0.0.0:{port}")
    print("="*80)
    print(f"  📊 Intervalo de velas: {INTERVALO_FIJO}s")
    print(f"  🎯 Entrada SIEMPRE en HH:MM:00 (inicio de vela)")
    print(f"  🕐 Zona horaria del BROKER: UTC-6")
    print(f"  🔒 Confianza mínima: {CONFIANZA_MINIMA}%")
    print(f"  📊 Mínimo patrones: {MIN_PATRONES} (SIEMPRE encuentra señales)")
    print("  🔍 ESCANEA TODOS los activos OTC")
    print("  🏆 Encuentra el MEJOR activo para operar")
    print("  📈 ¡SIEMPRE HAY UNA SEÑAL!")
    print("="*80)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
