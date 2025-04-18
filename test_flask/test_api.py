import requests
import json
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_URL = 'http://127.0.0.1:5000'

def test_health():
    url = f'{BASE_URL}/health'
    logger.info(f'Making GET request to: {url}')
    response = requests.get(url)
    logger.info(f'Response: {response.text}')
    print('Health check response:', response.json())

def test_register():
    url = f'{BASE_URL}/auth/register'
    data = {
        'email': 'test@example.com',
        'password': 'test123',
        'name': 'Test User'
    }
    logger.info(f'Making POST request to: {url}')
    logger.info(f'Request data: {json.dumps(data, indent=2)}')
    try:
        response = requests.post(url, json=data)
        logger.info(f'Response status: {response.status_code}')
        logger.info(f'Response headers: {dict(response.headers)}')
        logger.info(f'Response text: {response.text}')
        
        if response.ok:
            print('Register response:', response.json())
        else:
            print('Registration failed')
            
    except Exception as e:
        logger.error(f'Error during registration: {str(e)}')
        print('Error during registration:', str(e))

def test_login():
    url = f'{BASE_URL}/auth/login'
    data = {
        'email': 'test@example.com',
        'password': 'test123'
    }
    logger.info(f'Making POST request to: {url}')
    logger.info(f'Request data: {json.dumps(data, indent=2)}')
    try:
        response = requests.post(url, json=data)
        logger.info(f'Response status: {response.status_code}')
        logger.info(f'Response headers: {dict(response.headers)}')
        logger.info(f'Response text: {response.text}')
        
        if response.ok:
            print('Login response:', response.json())
        else:
            print('Login failed')
            
    except Exception as e:
        logger.error(f'Error during login: {str(e)}')
        print('Error during login:', str(e))

def test_create_presentation():
    url = f'{BASE_URL}/presentations'
    data = {
        'title': 'Test Presentation',
        'content': 'Test content'
    }
    logger.info(f'Making POST request to: {url}')
    logger.info(f'Request data: {json.dumps(data, indent=2)}')
    try:
        response = requests.post(url, json=data)
        logger.info(f'Response status: {response.status_code}')
        logger.info(f'Response headers: {dict(response.headers)}')
        logger.info(f'Response text: {response.text}')
        
        if response.ok:
            print('Create presentation response:', response.json())
        else:
            print('Create presentation failed')
            
    except Exception as e:
        logger.error(f'Error creating presentation: {str(e)}')
        print('Error creating presentation:', str(e))

if __name__ == '__main__':
    print('Testing health endpoint...')
    test_health()
    
    print('\nTesting registration...')
    test_register()
    
    print('\nTesting login...')
    test_login()
    
    print('\nTesting presentation creation...')
    test_create_presentation()
