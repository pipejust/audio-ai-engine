import base64
from reportlab.pdfgen import canvas
from pathlib import Path

pdf_path = "large_test.pdf"
c = canvas.Canvas(pdf_path)
for i in range(700):
    c.drawString(100, 750, f"Page {i} of large test PDF.")
    c.drawString(100, 700, "This is some dummy text to fill the page " * 50)
    c.showPage()
c.save()

print(f"Created {pdf_path}")
