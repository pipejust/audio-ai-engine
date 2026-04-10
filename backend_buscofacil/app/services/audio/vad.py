import math
import struct

def is_human_speech(pcm_bytes: bytes, sample_rate: int = 24000) -> bool:
    """
    Super-Algoritmo VAD Matemático ultrarrápido (< 1 milisegundo).
    Detecta si un fragmento de audio contiene voz humana evaluando Energía (RMS)
    y Frecuencia de cruces por cero (ZCR), filtrando ruidos externos, golpes o estática.
    """
    total_bytes = len(pcm_bytes)
    if total_bytes < 2:
        return False
        
    count = total_bytes // 2
    # Asegurarnos de usar la cantidad par de bytes
    clean_pcm = pcm_bytes[:count*2]
    
    try:
        shorts = struct.unpack(f"<{count}h", clean_pcm)
    except Exception:
        return False

    # 1. Energía (Volume)
    # Rango de shorts: -32768 a 32767
    rms = math.sqrt(sum(s*s for s in shorts) / count)
    
    # Threshold de volumen moderado alto (ajustado para ignorar ruido de fondo/ventiladores)
    if rms < 350:
        return False
        
    # 2. Zero Crossing Rate (ZCR) - Indicador de frecuencia principal
    crossings = sum(1 for i in range(1, count) if (shorts[i-1] >= 0) != (shorts[i] >= 0))
    zcr_per_sec = crossings * (sample_rate / count)
    
    # El habla humana típicamente cae en frecuencias modulares de cruce
    # Ruido blanco/viento tiene ZCR gigantes > 5000
    # Zumbidos graves / golpeteo tienen ZCR mínimos < 100
    if 250 < zcr_per_sec < 4500:
        # Pasa el filtro de voz humana!
        return True
        
    return False
