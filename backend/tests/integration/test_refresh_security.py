from fastapi.testclient import TestClient

def test_refresh_token_one_time_use(client:TestClient,registered_user:dict):
    payload=registered_user['payload']
    login=client.post('/api/v1/auth/login',data={'username':payload['email'],'password':payload['password']}).json()
    first=client.post('/api/v1/auth/refresh',json={'refresh_token':login['refresh_token']})
    assert first.status_code==200,first.text
    replay=client.post('/api/v1/auth/refresh',json={'refresh_token':login['refresh_token']})
    assert replay.status_code==401,replay.text
    new_token=first.json()['refresh_token']
    logout=client.post('/api/v1/auth/logout',json={'refresh_token':new_token},headers={'Authorization':'Bearer '+first.json()['access_token']})
    assert logout.status_code==200,logout.text
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':new_token}).status_code==401
