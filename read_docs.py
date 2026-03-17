import os
from PyPDF2 import PdfReader
import sys

try:
    import docx
except ImportError:
    docx = None

folder = "/Users/felipecortes/.gemini/antigravity/scratch/audio_ai_project/base de conocimiento"
out_file = "/Users/felipecortes/.gemini/antigravity/scratch/audio_ai_project/docs_content.txt"

with open(out_file, 'w', encoding='utf-8') as f:
    for filename in sorted(os.listdir(folder)):
        filepath = os.path.join(folder, filename)
        f.write(f"--- FILE: {filename} ---\n")
        if filename.endswith(".pdf"):
            try:
                reader = PdfReader(filepath)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        f.write(text + "\n")
            except Exception as e:
                f.write(f"Error reading PDF: {e}\n")
        elif filename.endswith(".docx"):
            if docx:
                try:
                    doc = docx.Document(filepath)
                    for para in doc.paragraphs:
                        f.write(para.text + "\n")
                except Exception as e:
                    f.write(f"Error reading DOCX: {e}\n")
            else:
                f.write("python-docx not installed.\n")
        f.write("\n\n")
print("Done extracting.")
