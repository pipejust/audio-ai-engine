import os
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from app.services.vector_store import VectorStoreManager

class RAGEngine:
    def __init__(self, vector_store: VectorStoreManager):
        self.vector_store = vector_store
        
        # Groq se usa aquí como el motor LLM super rápido.
        # Asegúrate de configurar GROQ_API_KEY en tu entorno.
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            print("⚠️ ADVERTENCIA: GROQ_API_KEY no encontrada. El LLM fallará si se invoca.")
            
        self.llm = ChatGroq(
            groq_api_key=groq_api_key,
            model_name="llama3-8b-8192", # Modelo muy rápido ideal para audio
            temperature=0.3,
            max_tokens=256 # Respuestas concisas para TTS
        )
        
        self.qa_chain = self._build_chain()

    def _build_chain(self):
        prompt_template = """ Eres un asistente virtual conversacional (de voz) amigable y conciso. 
        Usa los siguientes fragmentos de contexto que hemos extraído de nuestra base de conocimiento para responder la pregunta del usuario.
        REGLA DE ORO: Si no sabes la respuesta basándote en el contexto, simplemente di "No tengo información sobre eso en este momento".
        ESTILO OBLIGATORIO: Tus respuestas deben ser cortas, directas y en un tono conversacional natural, ya que serán leídas en voz alta a través de un motor de Text-to-Speech.
        
        Contexto:
        {context}
        
        Pregunta del usuario: {query}
        
        Respuesta (hablada):"""

        PROMPT = PromptTemplate(
            template=prompt_template, input_variables=["context", "query"]
        )

        chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vector_store.get_retriever(k=3),
            chain_type_kwargs={"prompt": PROMPT},
            return_source_documents=True
        )
        return chain

    def get_answer(self, query: str):
        """Retorna la respuesta generada y las fuentes consultadas"""
        print(f"Buscando respuesta para: '{query}'")
        try:
            res = self.qa_chain.invoke({"query": query})
            answer = res["result"]
            sources = [doc.metadata for doc in res["source_documents"]]
            return answer, sources
        except Exception as e:
            print(f"❌ Error en QA Chain: {e}")
            return "Lo siento, tuve un problema interno procesando tu consulta.", []
