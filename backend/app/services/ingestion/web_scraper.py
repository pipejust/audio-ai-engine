import json
import requests
from requests.exceptions import RequestException
from bs4 import BeautifulSoup
from langchain.docstore.document import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

class WebScraperIngestion:
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

    def scrape_url(self, url: str):
        """Descarga y extrae el texto puro de una URL"""
        print(f"Buscando recursos en URL: {url}")
        try:
            # Fake browser header para evitar bloqueos simples 403
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) MoshWasiBot/1.0'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            # Beautiful Soup para extraer texto sin HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Remover scripts y tags estilo para no meter basura al LLM
            for script in soup(["script", "style"]):
                script.extract()
            
            text = soup.get_text(separator=' ', strip=True)
            
            # Crear doc LangChain format con Metadata de la fuente original
            doc = Document(
                page_content=text,
                metadata={"source": url, "title": soup.title.string if soup.title else url}
            )
            
            # Devolver en chunks
            chunks = self.text_splitter.split_documents([doc])
            print(f"✅ Scraping finalizado. Creados {len(chunks)} fragmentos.")
            return chunks

        except RequestException as e:
            print(f"❌ Error descargando la URL {url}: {str(e)}")
            return []
