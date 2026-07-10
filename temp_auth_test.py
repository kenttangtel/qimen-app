import random
import string
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
username = 'testuser_' + ''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(6))
password = 'TestPass123!'
email = f'{username}@example.com'

print('TEST USER:', username)
resp = client.post('/api/v1/auth/register', json={'username': username, 'password': password, 'email': email})
print('REGISTER', resp.status_code, resp.text)
if resp.status_code == 200:
    resp2 = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    print('LOGIN', resp2.status_code, resp2.text)
    if resp2.status_code == 200:
        token = resp2.json().get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        resp3 = client.get('/api/v1/auth/me', headers=headers)
        print('ME', resp3.status_code, resp3.text)
