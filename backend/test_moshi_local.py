import torch
from transformers import pipeline
import time

def test_moshi_initialization():
    print("Iniciando prueba de carga de Moshi...")
    
    # Determinar el dispositivo
    device = "cpu"
    if torch.backends.mps.is_available():
        device = "mps" # Para Apple Silicon
    elif torch.cuda.is_available():
        device = "cuda"
        
    print(f"Device detectado: {device}")
    
    try:
        print("Descargando / Cargando pesos de Kyutai/moshika-hf...")
        print("Nota: Esto puede tardar varios minutos y requerir varios GBs de memoria.")
        
        start_time = time.time()
        # Moshi puede cargarse desde su pipeline en transformers
        pew_pipeline = pipeline(
            "text-generation", # En Transformers, Moshi opera primariamente autoregresivo sobre audio/texto
            model="kyutai/moshika-hf",
            device=device,
            torch_dtype=torch.float16 if device != "cpu" else torch.float32,
            trust_remote_code=True
        )
        end_time = time.time()
        
        print(f"✅ ¡Modelo Moshi cargado exitosamente en {end_time - start_time:.2f} segundos!")
        print("Moshi está listo para Full Duplex.")
        
    except Exception as e:
        print(f"❌ Error al cargar Moshi: {e}")
        print("Asegúrate de tener un TOKEN de HuggingFace válido y haber aceptado los términos de kyutai/moshika-hf o kyutai/moshika-pytorch")

if __name__ == "__main__":
    test_moshi_initialization()
