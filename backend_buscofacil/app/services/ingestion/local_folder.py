import os
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

class LocalFolderIngestion:
    def __init__(self, folder_path: str = "./data/knowledge"):
        self.folder_path = Path(folder_path)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, 
            chunk_overlap=200
        )

    def load_and_split_all(self):
        """Lee todos los PDFs y TXTs de la carpeta especificada y retorna los chunks"""
        if not self.folder_path.exists():
            self.folder_path.mkdir(parents=True)
            return []

        all_docs = []
        for file_path in self.folder_path.glob("*"):
            if file_path.suffix.lower() == ".pdf":
                loader = PyPDFLoader(str(file_path))
                docs = loader.load()
                all_docs.extend(docs)
                print(f"✅ Cargado PDF: {file_path.name}")
            elif file_path.suffix.lower() in [".txt", ".md"]:
                loader = TextLoader(str(file_path), encoding="utf-8")
                docs = loader.load()
                all_docs.extend(docs)
                print(f"✅ Cargado TXT/MD: {file_path.name}")

        if not all_docs:
            print("No se encontraron documentos para ingestar.")
            return []

        chunks = self.text_splitter.split_documents(all_docs)
        return chunks
