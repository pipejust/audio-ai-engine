from pypdf import PdfReader
reader = PdfReader('/tmp/test_output.pdf')
print(reader.pages[0].extract_text())
