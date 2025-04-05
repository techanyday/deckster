import requests
import json

# Login
login_data = {
    'email': 'test@example.com',
    'password': 'testpass123'
}

session = requests.Session()
response = session.post('http://localhost:5000/login', json=login_data)
print('Login response:', response.text)

# Generate presentation
form_data = {
    'mode': 'prompt',
    'input': 'Create a 3-slide presentation about artificial intelligence',
    'template': 'modern',
    'customStyles': json.dumps({
        'title': '#000000',
        'text': '#000000',
        'background': {
            'type': 'solid',
            'color': '#FFFFFF'
        }
    })
}

response = session.post('http://localhost:5000/generate', data=form_data)
print('Generate response:', response.text)
