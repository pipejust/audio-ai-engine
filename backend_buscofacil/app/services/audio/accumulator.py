class SentenceAccumulator:
    FIRST_EMIT_TOKENS  = 2    # tokens para primer chunk (arranque rápido)
    MIN_EMIT_TOKENS    = 1    # mínimo absoluto para emitir
    FORCE_EMIT_TOKENS  = 25   # máximo sin puntuación antes de forzar
    PUNCTUATION_END    = {'.', '?', '!', '…'}
    PUNCTUATION_PAUSE  = {',', ';'}
 
    def __init__(self, on_chunk):
        self.buffer   = []
        self.on_chunk = on_chunk  # callback async -> TTS
        self.first_emitted = False
 
    async def push(self, token: str):
        self.buffer.append(token)
        text = ''.join(self.buffer).strip()
        n = len(text.split())
 
        should_emit = False
 
        # Puntuación de fin de oración (Emite siempre que haya un punto, incluso si son 1-2 palabras)
        if text and text[-1] in self.PUNCTUATION_END:
            should_emit = True
            
        # Puntuación de pausa (coma, punto y coma)
        elif text and text[-1] in self.PUNCTUATION_PAUSE and n >= 12:
            should_emit = True
 
        # Forzado — evita bloqueo si el LLM no puntúa
        elif n >= self.FORCE_EMIT_TOKENS and ((token and token[-1].isspace()) or text[-1] in self.PUNCTUATION_END):
            should_emit = True
 
        if should_emit and len(text) >= self.MIN_EMIT_TOKENS:
            await self.on_chunk(text)
            self.buffer = []
            self.first_emitted = True
 
    async def flush(self):
        # Llamado al final del stream LLM
        text = ''.join(self.buffer).strip()
        if text:
            await self.on_chunk(text)
        self.buffer = []
