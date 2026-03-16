#!/bin/bash
# Crear pdf temporal
backend/venv/bin/python -c "
from fpdf import FPDF
pdf = FPDF()
pdf.add_page()
pdf.cell(200, 10, txt='Test', ln=1, align='C')
with open('test.pdf', 'wb') as f:
    f.write(pdf.output(dest='S').encode('latin1'))
"
# Hacer el POST y capturar salida y status
curl -i -X POST http://localhost:8000/upload/document \
  -F "file=@test.pdf;type=application/pdf" \
  -F "project_id=buscofacil" \
  --max-time 180
