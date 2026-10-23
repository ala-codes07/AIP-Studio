"""Secure email verification and recovery, with fake outbox; no SMTP dependency."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models.email_challenge import EmailChallenge
from app.services import email_codes


def signup(client, sent_codes, email='new@example.com'):
    r = client.post('/api/v1/auth/register', json={'email':email,'password':'InitialPassword123','organization_name':'Test Space'})
    assert r.status_code == 201, r.text
    assert r.json()['email_verified'] is False
    return sent_codes[(email, 'verify')]


def login(client, email='new@example.com', password='InitialPassword123'):
    return client.post('/api/v1/auth/login', data={'username':email,'password':password})


def test_email_required_to_login_and_code_single_use(client,sent_codes):
    code=signup(client,sent_codes)
    assert login(client).status_code==403
    assert client.post('/api/v1/auth/verify-email',json={'email':'new@example.com','code':'000000' if code!='000000' else '999999'}).status_code==422
    assert client.post('/api/v1/auth/verify-email',json={'email':'new@example.com','code':code}).status_code==200
    assert login(client).status_code==200
    assert client.post('/api/v1/auth/verify-email',json={'email':'new@example.com','code':code}).status_code==422


def test_bad_codes_are_locked_out(client,sent_codes,db):
    code=signup(client,sent_codes)
    bad='999999' if code!='999999' else '000000'
    for _ in range(5):
        assert client.post('/api/v1/auth/verify-email', json={'email':'new@example.com','code':bad}).status_code==422
    assert client.post('/api/v1/auth/verify-email',json={'email':'new@example.com','code':code}).status_code==422


def test_expiry_and_resend_throttle(client,sent_codes,db):
    code=signup(client,sent_codes)
    assert client.post('/api/v1/auth/resend-verification',json={'email':'new@example.com'}).status_code==429
    ch=db.scalar(select(EmailChallenge))
    ch.expires_at = datetime.now(timezone.utc)-timedelta(seconds=3)
    db.commit()
    assert client.post('/api/v1/auth/verify-email',json={'email':'new@example.com','code':code}).status_code==422
    ch.created_at = datetime.now(timezone.utc)-timedelta(minutes=2)
    db.commit()
    assert client.post('/api/v1/auth/resend-verification',json={'email':'new@example.com'}).status_code==200
    assert sent_codes[('new@example.com','verify')] != code
    assert client.post('/api/v1/auth/verify-email',json={'email':'new@example.com','code':code}).status_code==422


def test_forgot_password_does_not_disclose_accounts(client,sent_codes):
    signup(client,sent_codes)
    known=client.post('/api/v1/auth/forgot-password',json={'email':'new@example.com'})
    unknown=client.post('/api/v1/auth/forgot-password',json={'email':'unknown@example.com'})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_reset_password_revokes_refresh_and_existing_access(client,sent_codes):
    signup(client,sent_codes)
    code=sent_codes[('new@example.com','verify')]
    client.post('/api/v1/auth/verify-email',json={'email':'new@example.com','code':code})
    previous=login(client).json()
    assert client.get('/api/v1/auth/me',headers={'Authorization':f'Bearer {previous["access_token"]}'}).status_code==200
    assert client.post('/api/v1/auth/forgot-password',json={'email':'new@example.com'}).status_code==200
    reset_code=sent_codes[('new@example.com','reset')]
    assert client.post('/api/v1/auth/reset-password',json={'email':'new@example.com','code':reset_code,'new_password':'CompletelyDifferent123'}).status_code==200
    assert client.get('/api/v1/auth/me',headers={'Authorization':f'Bearer {previous["access_token"]}'}).status_code==401
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':previous['refresh_token']}).status_code==401
    assert login(client).status_code==401
    assert login(client,password='CompletelyDifferent123').status_code==200
    assert client.post('/api/v1/auth/reset-password',json={'email':'new@example.com','code':reset_code,'new_password':'DifferentAgain123'}).status_code==422


def test_authenticated_change_password_invalidates_sessions(client,sent_codes):
    signup(client,sent_codes)
    client.post('/api/v1/auth/verify-email',json={'email':'new@example.com','code':sent_codes[('new@example.com','verify')]})
    tokens=login(client).json()
    headers={'Authorization':f'Bearer {tokens["access_token"]}'}
    assert client.post('/api/v1/auth/change-password',headers=headers,json={'current_password':'wrong','new_password':'NewSecret1234'}).status_code==401
    assert client.post('/api/v1/auth/change-password',headers=headers,json={'current_password':'InitialPassword123','new_password':'NewSecret1234'}).status_code==200
    assert client.get('/api/v1/auth/me',headers=headers).status_code==401
    assert login(client,password='NewSecret1234').status_code==200


def test_keywords_come_only_from_fetched_content(monkeypatch):
    from app.services import seo_engine
    def fake(url, **kwargs):
        if url.endswith('/robots.txt'):
            return seo_engine.FetchResult(url,200,'text/plain','User-agent: *\nAllow: /')
        return seo_engine.FetchResult(url,200,'text/html','<html lang="fa"><head><title>میکروسمنت کف و دیوار</title><meta name="description" content="میکروسمنت مناسب طراحی داخلی"></head><body><h1>میکروسمنت کف و دیوار</h1><p>میکروسمنت برای کف مناسب است. میکروسمنت برای دیوار زیباست. میکروسمنت در طراحی داخلی بسیار کاربرد دارد.</p><script>buy drugs buy drugs</script></body></html>')
    monkeypatch.setattr(seo_engine,'fetch_public_page',fake)
    result=seo_engine.run_audit('https://example.com/')
    analysis=result['summary']['content_analysis']
    assert result['pages_scanned']==1
    assert analysis['pages'][0]['word_count']>0
    assert any('میکروسمنت' in x['term'] for x in analysis['keywords'])
    assert all('drugs' not in x['term'] for x in analysis['keywords'])
    assert analysis['recommendations']
