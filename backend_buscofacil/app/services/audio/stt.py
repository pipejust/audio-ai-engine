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

    def transcribe_audio(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        """Convierte bytes de audio a texto usando Groq Whisper"""
        try:
            # Groq requiere un archivo con nombre, así que wrappeamos el buffer
            file_tuple = (filename, audio_bytes)
            
            completion = self.client.audio.transcriptions.create(
                file=file_tuple,
                model=self.model,
                language="es",
                response_format="json",
                temperature=0.0
            )
            
            text = completion.text.strip()
            
            # Limpiar puntuación para comparar
            clean_text = text.lower().replace(".", "").replace(",", "").replace("¡", "").replace("!", "").replace("¿", "").replace("?", "").strip()
            
            # Si el texto es demasiado corto (solo ruido o 1 letra) lo ignoramos
            if len(clean_text) <= 1:
                return ""
            
            # Filtro extendido de alucinaciones comunes de Whisper (Español e Inglés)
            hallucinations = [
                "gracias", "subtítulos", "amén", "gracias por ver", "suscríbete", 
                "thank you", "thanks", "subtitles", "you", "oh", "ah"
            ]
            
            if clean_text in hallucinations:
                print(f"🛑 STT Filtrado (Alucinación detectada): {text}")
                return ""
                
            return text
        except Exception as e:
            print(f"❌ Error en STT (Groq Whisper): {e}")
            return ""
