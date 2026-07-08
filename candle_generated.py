"""
Módulo para procesamiento de velas generadas en tiempo real desde IQ Option WebSocket.
Versión optimizada para alta frecuencia (HFT) con mínima latencia.
"""

import logging
import time
from typing import Dict, Any, Optional, Callable

import iqoptionapi.constants as OP_code

logger = logging.getLogger(__name__)

# ============================================================================
# ESTRUCTURAS OPTIMIZADAS
# ============================================================================

# Diccionario inverso para búsqueda O(1)
_INVERSE_ACTIVES: Dict[int, str] = {
    active_id: active_name 
    for active_name, active_id in OP_code.ACTIVES.items()
}

# ============================================================================
# MODELO DE DATOS OPTIMIZADO
# ============================================================================

class CandleData:
    """Vela enriquecida con __slots__ para máxima eficiencia de memoria."""
    
    __slots__ = (
        'active', 'active_id', 'timeframe', 'timestamp',
        'open', 'close', 'high', 'low', 'volume',
        'body_size', 'body_ratio', 'upper_wick', 'lower_wick',
        'total_range', 'mid_price', 'spread', 'volatility',
        'candle_type', 'is_bullish', 'strength',
        'hash_id', 'session', 'raw_data'
    )
    
    def __init__(self, active: str, active_id: int, timeframe: int, timestamp: int,
                 open_price: float, close_price: float, high_price: float, 
                 low_price: float, volume: float = 0.0):
        # Datos básicos
        self.active = active
        self.active_id = active_id
        self.timeframe = timeframe
        self.timestamp = timestamp
        self.open = open_price
        self.close = close_price
        self.high = high_price
        self.low = low_price
        self.volume = volume
        self.raw_data = {}
        
        # Cálculos de métricas
        self._calculate_metrics()
    
    def _calculate_metrics(self) -> None:
        """Calcula métricas básicas de la vela."""
        self.is_bullish = self.close >= self.open
        self.body_size = abs(self.close - self.open)
        self.total_range = self.high - self.low
        
        if self.total_range > 0:
            self.body_ratio = self.body_size / self.total_range
            if self.is_bullish:
                self.upper_wick = self.high - self.close
                self.lower_wick = self.open - self.low
            else:
                self.upper_wick = self.high - self.open
                self.lower_wick = self.close - self.low
        else:
            self.body_ratio = 0.0
            self.upper_wick = 0.0
            self.lower_wick = 0.0
        
        self.mid_price = (self.high + self.low) / 2
        self.spread = self.total_range
        self.volatility = self.spread / self.mid_price if self.mid_price > 0 else 0.0
        self.strength = self.body_ratio
        
        # Clasificación simple
        self.candle_type = self._classify_candle()
        
        # Identificador único
        self.hash_id = f"{self.active_id}:{self.timeframe}:{self.timestamp}"
        
        # Sesión de mercado (usando time.gmtime para eficiencia)
        tm = time.gmtime(self.timestamp)
        hour = tm.tm_hour
        if hour < 6:
            self.session = "OFF_HOURS"
        elif hour < 12:
            self.session = "ASIA"
        elif hour < 18:
            self.session = "EUROPE"
        else:
            self.session = "AMERICA"
    
    def _classify_candle(self) -> str:
        """Clasifica la vela de manera eficiente."""
        if self.body_size == 0:
            return "DOJI"
        if self.body_ratio >= 0.95:
            return "MARUBOZU"
        if self.body_ratio <= 0.3:
            return "SPINNING_TOP"
        return "BULLISH" if self.is_bullish else "BEARISH"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para compatibilidad."""
        return {
            'active': self.active,
            'active_id': self.active_id,
            'timeframe': self.timeframe,
            'timestamp': self.timestamp,
            'open': self.open,
            'close': self.close,
            'high': self.high,
            'low': self.low,
            'volume': self.volume,
            'body_size': self.body_size,
            'body_ratio': self.body_ratio,
            'upper_wick': self.upper_wick,
            'lower_wick': self.lower_wick,
            'total_range': self.total_range,
            'mid_price': self.mid_price,
            'spread': self.spread,
            'volatility': self.volatility,
            'candle_type': self.candle_type,
            'is_bullish': self.is_bullish,
            'strength': self.strength,
            'hash_id': self.hash_id,
            'session': self.session
        }

# ============================================================================
# FUNCIÓN PRINCIPAL OPTIMIZADA
# ============================================================================

def candle_generated_realtime(
    api: Any,
    message: Dict[str, Any],
    dict_queue_add: Callable
) -> Optional[CandleData]:
    """
    Procesa mensajes de velas generadas en tiempo real con mínima latencia.
    """
    # Validación mínima
    if not isinstance(message, dict) or message.get("name") != "candle-generated":
        return None
    
    msg = message.get("msg")
    if not isinstance(msg, dict):
        return None
    
    # Extracción rápida con validación esencial
    try:
        active_id = int(msg['active_id'])
        active = _INVERSE_ACTIVES[active_id]  # O(1) lookup, valida existencia
        timeframe = int(msg['size'])
        timestamp = int(msg['from'])
        open_price = float(msg['open'])
        close_price = float(msg['close'])
        high_price = float(msg['high'])
        low_price = float(msg['low'])
        volume = float(msg.get('volume', 0.0))
    except (KeyError, ValueError, TypeError):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Error extrayendo datos de vela")
        return None
    
    # Validación de consistencia básica
    if not (low_price <= min(open_price, close_price) <= 
            max(open_price, close_price) <= high_price):
        if logger.isEnabledFor(logging.WARNING):
            logger.warning(f"Precios inconsistentes: {active}")
        return None
    
    # Creación de la vela (directa, sin pool)
    candle = CandleData(
        active=active,
        active_id=active_id,
        timeframe=timeframe,
        timestamp=timestamp,
        open_price=open_price,
        close_price=close_price,
        high_price=high_price,
        low_price=low_price,
        volume=volume
    )
    candle.raw_data = msg
    
    # Almacenamiento (manteniendo compatibilidad)
    try:
        maxdict = api.real_time_candles_maxdict_table.get(
            active, {}
        ).get(timeframe, 1000)
        
        api.real_time_candles.setdefault(active, {}).setdefault(timeframe, {})
        
        dict_queue_add(
            api.real_time_candles,
            maxdict,
            active,
            timeframe,
            timestamp,
            msg
        )
        
        api.candle_generated_check.setdefault(active, {})[timeframe] = True
        
    except Exception as e:
        if logger.isEnabledFor(logging.ERROR):
            logger.error(f"Error almacenando {active}: {e}")
        # Continuamos, la vela ya fue procesada
    
    # Callback opcional con logging de errores
    if hasattr(api, '_on_candle_processed'):
        try:
            api._on_candle_processed(candle)
        except Exception as e:
            if logger.isEnabledFor(logging.ERROR):
                logger.error(f"Error en callback _on_candle_processed: {e}", exc_info=True)
    
    return candle

# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def get_active_name(active_id: int) -> Optional[str]:
    """Obtiene el nombre del activo (O(1))."""
    return _INVERSE_ACTIVES.get(active_id)

def enrich_candle_data(
    active: str,
    active_id: int,
    timeframe: int,
    timestamp: int,
    open: float,
    close: float,
    high: float,
    low: float,
    volume: float = 0.0
) -> CandleData:
    """Crea CandleData para compatibilidad."""
    return CandleData(
        active=active,
        active_id=active_id,
        timeframe=timeframe,
        timestamp=timestamp,
        open_price=open,
        close_price=close,
        high_price=high,
        low_price=low,
        volume=volume
    )

# ============================================================================
# EXPORTS PARA COMPATIBILIDAD
# ============================================================================

__all__ = [
    'candle_generated_realtime',
    'get_active_name',
    'enrich_candle_data',
    'CandleData'
]
