import requests

url = "https://moshwasi-audio-api.onrender.com/upload/document"
files = {'file': ('test.pdf', b'dummy content', 'application/pdf')}
data = {'project_id': 'buscofacil'}

print("Sending request...")
response = requests.post(url, files=files, data=data)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
