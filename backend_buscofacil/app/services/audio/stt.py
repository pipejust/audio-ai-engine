import os
from groq import Groq
from io import BytesIO

class STTEngine:
    def __init__(self):
        """Inicializa el motor Groq STT (Whisper)"""
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            print("⚠️ ADVERTENCIA: GROQ_API_KEY no encontrada para el STT.")
        self.client = Groq(api_key=groq_api_key)
        self.model = "whisper-large-v3-turbo" # Muy rápido

    def transcribe_audio(self, audio_bytes: bytes, filename: str = "audio.wav", language: str = "es") -> str:
        """Convierte bytes de audio a texto usando Groq Whisper.

        language: hint de idioma para Whisper (default 'es' para BuscoFácil).
        Pasar None para detección automática (más propenso a alucinaciones en audio corto).
        """
        try:
            # Groq requiere un archivo con nombre, así que wrappeamos el buffer
            file_tuple = (filename, audio_bytes)

            create_kwargs = dict(
                file=file_tuple,
                model=self.model,
                response_format="json",
                temperature=0.0,
            )
            if language:
                create_kwargs["language"] = language

            completion = self.client.audio.transcriptions.create(**create_kwargs)
            
            # Whisper agrega puntuación automáticamente ("No." → "No").
            # Limpiar al salir para que comparaciones exactas funcionen en todo el sistema.
            text = completion.text.strip().rstrip(".,!?¡¿").strip()
            
            # Limpiar puntuación para comparar
            clean_text = text.lower().replace(".", "").replace(",", "").replace("¡", "").replace("!", "").replace("¿", "").replace("?", "").strip()
            
            # Si el texto es demasiado corto (solo ruido o 1 letra) lo ignoramos
            if len(clean_text) <= 1:
                return ""
            
            # Filtro extendido de alucinaciones comunes de Whisper (Español e Inglés)
            hallucinations = [
                "gracias", "subtítulos", "amén", "gracias por ver", "suscríbete", 
                "thank you", "thanks", "subtitles", "you", "oh", "ah",
                "hasta la próxima", "hasta la proxima", "nos vemos", "muchas gracias"
            ]
            
            if clean_text in hallucinations:
                print(f"🛑 STT Filtrado (Alucinación detectada): {text}")
                return ""
                
            return text
        except Exception as e:
            print(f"❌ Error en STT (Groq Whisper): {e}")
            return ""
