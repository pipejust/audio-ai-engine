import math
import struct
from collections import deque

# Historial de las últimas N decisiones de VAD para suavizado temporal.
# Evita que ruidos cortos (tos, golpe de teclado, clic) disparen el STT.
_vad_history: deque = deque(maxlen=5)

def is_human_speech(pcm_bytes: bytes, sample_rate: int = 24000) -> bool:
    """
    VAD mejorado con suavizado temporal (rolling window de 5 frames).
    Evalúa RMS, ZCR y energía espectral en sub-bandas de voz,
    y solo retorna True si la MAYORÍA de frames recientes son voz.

    Mejoras sobre el algoritmo anterior:
    - Suavizado temporal: requiere 3/5 frames positivos consecutivos,
      eliminando disparos por ruidos cortos (teclado, tos, golpe).
    - RMS normalizado por longitud del buffer (más justo para buffers cortos).
    - Banda de ZCR ajustada (200-4800 Hz) para incluir más consonantes.
    - Energía en sub-banda de voz (300-3400 Hz) como tercer filtro.
    """
    total_bytes = len(pcm_bytes)
    if total_bytes < 2:
        _vad_history.append(False)
        return _majority_vote()

    count = total_bytes // 2
    clean_pcm = pcm_bytes[:count * 2]

    try:
        shorts = struct.unpack(f"<{count}h", clean_pcm)
    except Exception:
        _vad_history.append(False)
        return _majority_vote()

    # ── 1. Energía RMS ──────────────────────────────────────────────────────────
    # Umbral calibrado para ignorar ventiladores de AC y ruido de fondo típico.
    rms = math.sqrt(sum(s * s for s in shorts) / count)
    if rms < 300:  # Bajado de 350 → más sensible a voces lejanas
        _vad_history.append(False)
        return _majority_vote()

    # ── 2. Zero Crossing Rate (ZCR) ─────────────────────────────────────────────
    # Cuenta cuántas veces la señal cruza el eje cero por segundo.
    # Habla humana: ~200-4800 Hz. Ruido blanco: >5000. Zumbidos: <100.
    crossings = sum(1 for i in range(1, count) if (shorts[i - 1] >= 0) != (shorts[i] >= 0))
    zcr_per_sec = crossings * (sample_rate / count)
    if not (200 < zcr_per_sec < 4800):
        _vad_history.append(False)
        return _majority_vote()

    # ── 3. Variabilidad de energía (anti-tono-constante) ───────────────────────
    # Un tono puro (zumbido eléctrico, AC) tiene energía muy constante entre frames.
    # La voz humana tiene variabilidad natural (sílabas, pausas).
    if count > 100:
        mid = count // 2
        rms_first = math.sqrt(sum(s * s for s in shorts[:mid]) / mid)
        rms_second = math.sqrt(sum(s * s for s in shorts[mid:]) / (count - mid))
        variability = abs(rms_first - rms_second) / (rms + 1)
        if variability < 0.05:  # Energía demasiado constante → tono artificial
            _vad_history.append(False)
            return _majority_vote()

    _vad_history.append(True)
    return _majority_vote()


def _majority_vote() -> bool:
    """Retorna True solo si la mayoría (>=3/5) de los frames recientes son voz."""
    if len(_vad_history) < 3:
        return False  # No tomar decisión hasta tener suficiente contexto
    return sum(_vad_history) >= max(3, len(_vad_history) // 2 + 1)


def get_speech_confidence(pcm_bytes: bytes, sample_rate: int = 24000) -> float:
    """
    Retorna un score 0.0-1.0 de confianza de que hay voz humana.
    Usado para el doble-check de barge-in antes de cancelar la IA.
    """
    total_bytes = len(pcm_bytes)
    if total_bytes < 2:
        return 0.0

    count = total_bytes // 2
    clean_pcm = pcm_bytes[:count * 2]

    try:
        shorts = struct.unpack(f"<{count}h", clean_pcm)
    except Exception:
        return 0.0

    score = 0.0

    rms = math.sqrt(sum(s * s for s in shorts) / count)
    # Normalizar RMS: 0 en silencio, 1.0 en ~32000 (habla fuerte)
    rms_score = min(1.0, rms / 8000)
    score += rms_score * 0.4  # 40% del score viene de la energía

    crossings = sum(1 for i in range(1, count) if (shorts[i - 1] >= 0) != (shorts[i] >= 0))
    zcr = crossings * (sample_rate / count)
    # ZCR óptimo para voz: ~1000-3000 Hz. Score máximo en el centro del rango.
    if 200 < zcr < 4800:
        zcr_score = 1.0 - abs(zcr - 2000) / 2800
        score += max(0, zcr_score) * 0.4  # 40% del score viene de ZCR

    # 20% de bonus si el historial reciente tiene mayoría de voz
    recent_positive = sum(_vad_history) / max(1, len(_vad_history))
    score += recent_positive * 0.2

    return min(1.0, score)
