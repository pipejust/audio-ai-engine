import requests
from fpdf import FPDF

pdf = FPDF()
pdf.add_page()
pdf.set_font("Arial", size=12)
pdf.cell(200, 10, txt="Hello World!", ln=1, align="C")
pdf_bytes = pdf.output(dest='S').encode('latin1')

url = "https://moshwasi-audio-api.onrender.com/upload/document"
files = {'file': ('test.pdf', pdf_bytes, 'application/pdf')}
data = {'project_id': 'buscofacil'}

print("Sending request to Render...")
try:
    response = requests.post(url, files=files, data=data, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
