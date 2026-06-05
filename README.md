# 🤖 IQ Option Bot API — Guía Completa

## ¿Qué hace esto?

Este servidor corre en **tu PC** y actúa como puente entre **Lovable** e **IQ Option**.  
Lovable usa tu **API Key personal** para consultarle todo lo que necesita.

```
Lovable  ──(API Key)──▶  Tu PC (servidor)  ──▶  IQ Option
```

---

## ⚡ Inicio en 3 pasos

### Paso 1 — Asegúrate de tener Python
Descarga Python 3.8+ desde https://python.org si no lo tienes.

### Paso 2 — Instala y arranca el servidor
```bash
python instalar.py
```
Esto instala todo y arranca el servidor automáticamente.

### Paso 3 — Copia tu API Key y pégala en Lovable
```
l2nHjjc2pS5I0VuLjaJmquPNsR87Sa1glQqJmjRNHWE
```
En Lovable → Secrets → Nuevo secreto:
- **Nombre:** `CLAVE_API_IQOPTION`
- **Valor:** (pega la clave)

---

## 🌐 URL base del servidor
```
http://localhost:8000
```

> Si quieres que Lovable acceda desde internet (no solo desde tu PC),
> usa ngrok: `ngrok http 8000` y usa la URL que te da.

---

## 📡 Todos los endpoints

Cada llamada necesita la API Key. Puedes enviarla de dos formas:
```
Header:    X-API-Key: l2nHjjc2pS5I0VuLjaJmquPNsR87Sa1glQqJmjRNHWE
URL param: ?api_key=l2nHjjc2pS5I0VuLjaJmquPNsR87Sa1glQqJmjRNHWE
```

---

### 1. `POST /iq/conectar` — Login en IQ Option
```json
{
  "email":    "tu@email.com",
  "password": "tuContraseña",
  "cuenta":   "PRACTICE"
}
```
`cuenta` puede ser `"PRACTICE"` (demo) o `"REAL"`

**Respuesta:**
```json
{
  "ok":     true,
  "email":  "tu@email.com",
  "cuenta": "PRACTICE",
  "saldo":  10000.00
}
```

---

### 2. `GET /iq/estado` — Ver saldo y estado
```
GET /iq/estado
```
**Respuesta:**
```json
{
  "conectado":     true,
  "cuenta_activa": "PRACTICE",
  "saldo_activo":  9847.50,
  "saldos": {
    "demo": 9847.50,
    "real": 250.00
  }
}
```

---

### 3. `GET /iq/activos` — Activos disponibles
```
GET /iq/activos?tipo=all&solo_abiertos=1
```
Parámetros:
- `tipo`: `all` | `binary` | `digital`
- `solo_abiertos`: `1` para ver solo los que están abiertos ahora

**Respuesta:**
```json
{
  "activos": {
    "EURUSD":     { "es_otc": false, "tipos": { "turbo_1": { "abierto": true } } },
    "EURUSD-OTC": { "es_otc": true,  "tipos": { "turbo_1": { "abierto": true } } }
  }
}
```

---

### 4. `GET /iq/velas` — Velas históricas
```
GET /iq/velas?activo=EURUSD&intervalo=60&cantidad=100
```
- `intervalo` en segundos: `60`=1min, `300`=5min, `3600`=1h
- `cantidad`: cuántas velas traer (máximo ~1000)

---

### 5. `GET /iq/velas/live` — Velas en tiempo real
```
GET /iq/velas/live?activo=EURUSD&intervalo=60
```
Devuelve las últimas 5 velas del stream en vivo.

---

### 6. `POST /iq/senal` — ⭐ Señal de trading
```json
{
  "activo":         "EURUSD-OTC",
  "intervalo":      60,
  "duracion":       1,
  "cantidad_velas": 100,
  "estrategia":     "auto"
}
```

**Estrategias disponibles:**
| Valor | Cuándo se usa (modo auto) |
|-------|--------------------------|
| `auto` | El bot elige según la volatilidad del mercado |
| `fibonacci` | Mercado con volatilidad media |
| `bollinger` | Mercado muy volátil |
| `tendencia` | Mercado tranquilo/trending |
| `macd` | Siempre MACD + EMA |
| `rsi` | Siempre RSI |

**Respuesta:**
```json
{
  "activo":              "EURUSD-OTC",
  "es_otc":              true,
  "intervalo_vela":      "60s",
  "duracion_op":         "1 min",
  "estrategia_usada":    "fibonacci",
  "volatilidad_mercado": "media",
  "senal":               "BUY",
  "confianza":           "78%",
  "hora_entrada":        "14:32:05 UTC",
  "proxima_vela_en":     "23s",
  "activo_abierto":      true,
  "rentabilidad":        "82.0%",
  "analisis": {
    "razones": [
      "RSI sobrevendido (28.5) → compra",
      "Precio en soporte Fibonacci 61.8% → zona de rebote alcista",
      "Patrón: Martillo → BUY (fuerza 75%)"
    ],
    "indicadores": { "rsi": 28.5, "ema9": 1.08412, ... },
    "fibonacci":   { "niveles": {...}, "zona_actual": "61.8" },
    "patrones":    [{ "patron": "Martillo", "tipo": "BUY" }]
  }
}
```

---

### 7. `GET /iq/profit` — Rentabilidad del activo
```
GET /iq/profit?activo=EURUSD
```
```json
{ "profit_turbo": 82.0, "profit_binary": 79.5 }
```

---

### 8. `GET /demo/senal` — Demo sin login
```
GET /demo/senal?activo=EURUSD&intervalo=60&estrategia=auto
```
Genera velas sintéticas y hace el análisis real. Sirve para probar
Lovable sin necesitar credenciales de IQ Option.

---

## 🔗 Código para Lovable

```javascript
const BASE = "http://localhost:8000";
const KEY  = import.meta.env.VITE_CLAVE_API_IQOPTION;
const HEADERS = { "Content-Type": "application/json", "X-API-Key": KEY };

// ── Conectar ─────────────────────────────────────────────────
async function conectarIQ(email, password, cuenta = "PRACTICE") {
  const r = await fetch(`${BASE}/iq/conectar`, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify({ email, password, cuenta })
  });
  return r.json();
}

// ── Ver saldo ────────────────────────────────────────────────
async function verSaldo() {
  const r = await fetch(`${BASE}/iq/estado`, { headers: HEADERS });
  return r.json();
}

// ── Activos abiertos ─────────────────────────────────────────
async function activosAbiertos() {
  const r = await fetch(`${BASE}/iq/activos?solo_abiertos=1`, { headers: HEADERS });
  return r.json();
}

// ── Obtener señal ────────────────────────────────────────────
async function obtenerSenal(activo, intervalo, duracion, estrategia = "auto") {
  const r = await fetch(`${BASE}/iq/senal`, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify({
      activo, intervalo, duracion,
      cantidad_velas: 100,
      estrategia
    })
  });
  const data = await r.json();
  return data;
  // data.senal          → "BUY" | "SELL" | "NEUTRAL"
  // data.confianza      → "78%"
  // data.hora_entrada   → "14:32:05 UTC"
  // data.es_otc         → true/false
  // data.volatilidad_mercado → "alta" | "media" | "baja"
  // data.estrategia_usada    → estrategia que eligió el bot
}
```

---

## 🛡️ Límites de seguridad

Este API **SOLO LECTURA**:
- ✅ Obtener velas, precios, activos
- ✅ Ver saldo demo y real
- ✅ Generar señales de análisis técnico
- ❌ No puede comprar ni vender
- ❌ No puede modificar tu cuenta

---

## ⚠️ Advertencia

Solo para estudio personal. El trading implica riesgo de pérdida de capital.
