import requests

session = requests.Session()

url = 'https://mypayindia.com/api/v2/auth/login'
data = {
    'username': 'spebelgenenst',
    'password': 'WuWMyPayIndia',
    'totp_code': '207682'
}

response = session.post(url, json = data).json()

print(response)

session_id = response.get("data").get("session_id")

print(session_id)

url = 'https://mypayindia.com/api/v2/user/session/invalidate'
data = {
    'session_id': session_id
}

response = session.post(url, json = data).json()

print(response)