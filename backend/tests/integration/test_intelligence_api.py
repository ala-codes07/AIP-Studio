"""Website intelligence regressions: access control, scans and exports."""
from __future__ import annotations
import uuid
from fastapi.testclient import TestClient
from app.services.seo_engine import FetchResult, analyze_html, validate_target, public_addresses
from app.core.exceptions import ValidationError


def sample_report():
    response = FetchResult('https://example.com/', 200, 'text/html', '<html lang="en"><head><title>Example</title><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><h1>Hello</h1><img src="image.jpg"><a href="/about">About</a></body></html>')
    findings, parser = analyze_html(response)
    return {"score":79,"pages_scanned":1,"issues_count":len(findings),"summary":{"pages":[{"url":response.url,"status":200,"title":parser.title,"issues":len(findings)}],"severity_counts":{"medium":2},"methodology":"Deterministic HTML/HTTP checks"},"findings":findings}


def test_html_checks_have_page_evidence():
    results = sample_report()
    rules = {f['rule'] for f in results['findings']}
    assert {'missing_description','missing_canonical','missing_image_alt'} <= rules
    assert all(x['page_url']=='https://example.com/' for x in results['findings'])


def test_alt_empty_is_valid_for_decorative_images():
    f,_ = analyze_html(FetchResult('https://example.com/',200,'text/html','<html lang="en"><head><title>Yes</title><meta name="viewport" content="width=device-width"></head><body><h1>H</h1><img src="a.jpg" alt=""></body></html>'))
    assert not any(x['rule']=='missing_image_alt' for x in f)


def test_invalid_targets_rejected():
    for target in ['http://localhost/','http://127.0.0.1/','http://192.168.0.1/','file:///etc/passwd','http://example.com:8080/','http://user:pass@example.com/', 'http://myhost.local/', 'http://a.com/\nInjected: x']:
        try:validate_target(target)
        except ValidationError:pass
        else:raise AssertionError(f'Unsafe target accepted: {target}')


def test_internal_dns_rejected(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k: [(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.8',0))])
    try:public_addresses('example.com')
    except ValidationError:pass
    else:raise AssertionError('Private DNS result should be blocked')


def test_websites_and_reports_are_tenant_isolated(client:TestClient,auth_headers:dict,monkeypatch,sent_codes):
    from app.api.v1.endpoints import intelligence
    monkeypatch.setattr(intelligence,'run_audit',lambda url:sample_report())
    org=client.get('/api/v1/organizations',headers=auth_headers).json()[0]['id']
    created=client.post(f'/api/v1/organizations/{org}/websites',json={'name':'Example Domain','url':'https://example.com/'},headers=auth_headers)
    assert created.status_code==201,created.text
    website=created.json()
    scan=client.post(f'/api/v1/websites/{website["id"]}/audits',headers=auth_headers)
    assert scan.status_code==201,scan.text
    audit_id=scan.json()['id']
    report=client.get(f'/api/v1/audits/{audit_id}',headers=auth_headers)
    assert report.status_code==200,report.text
    assert report.json()['audit']['issues_count']>=2
    assert client.get(f'/api/v1/audits/{audit_id}/export.csv',headers=auth_headers).status_code==200
    client.post('/api/v1/auth/register',json={'email':'stranger@example.com','password':'OtherPass123'})
    client.post('/api/v1/auth/verify-email',json={'email':'stranger@example.com','code':sent_codes[('stranger@example.com','verify')]})
    login=client.post('/api/v1/auth/login',data={'username':'stranger@example.com','password':'OtherPass123'}).json()
    stranger={'Authorization':f'Bearer {login["access_token"]}'}
    assert client.get(f'/api/v1/organizations/{org}/websites',headers=stranger).status_code==404
    assert client.get(f'/api/v1/websites/{website["id"]}/audits',headers=stranger).status_code==404
    assert client.post(f'/api/v1/websites/{website["id"]}/audits',headers=stranger).status_code==404
    assert client.get(f'/api/v1/audits/{audit_id}',headers=stranger).status_code==404
    assert client.get(f'/api/v1/audits/{audit_id}/export.csv',headers=stranger).status_code==404
    assert client.delete(f'/api/v1/websites/{website["id"]}',headers=stranger).status_code==404
    assert client.get(f'/api/v1/audits/{audit_id}/ai-analysis',headers=stranger).status_code in (404,405)


def test_frontend_routes(client:TestClient):
    page=client.get('/')
    assert page.status_code==200,page.text
    assert 'AIP Studio' in page.text
    assert client.get('/static/styles.css').status_code==200
    assert client.get('/static/app.js').status_code==200


def test_free_local_evidence_plan_requires_no_api_key(client:TestClient,auth_headers:dict,monkeypatch):
    from app.api.v1.endpoints import intelligence
    monkeypatch.setattr(intelligence,'run_audit',lambda url:sample_report())
    org=client.get('/api/v1/organizations',headers=auth_headers).json()[0]['id']
    site=client.post(f'/api/v1/organizations/{org}/websites',json={'name':'Example','url':'https://example.com'},headers=auth_headers).json()
    audit=client.post(f'/api/v1/websites/{site["id"]}/audits',headers=auth_headers).json()
    response=client.post(f'/api/v1/audits/{audit["id"]}/ai-analysis',headers=auth_headers)
    assert response.status_code==200, response.text
    assert response.json()['mode']=='rules'
    assert 'EVIDENCE-BASED SEO ACTION PLAN' in response.json()['analysis']

def test_real_scanner_flow_with_stubbed_public_responses(monkeypatch):
    from app.services import seo_engine
    requested=[]
    def fake_fetch(url, **kwargs):
        requested.append(url)
        if url.endswith('/robots.txt'):
            return FetchResult(url, 200, 'text/plain', 'User-agent: *\nAllow: /\n')
        if url.endswith('/about'):
            return FetchResult(url, 200, 'text/html', '<html lang="en"><head><title>About</title></head><body><h1>About</h1></body></html>')
        return FetchResult(url, 200, 'text/html', '<html lang="en"><head><title>Home</title></head><body><h1>Welcome</h1><a href="/about">About</a><a href="https://other.example/">External</a></body></html>')
    monkeypatch.setattr(seo_engine,'fetch_public_page',fake_fetch)
    result=seo_engine.run_audit('https://example.com/',max_pages=3)
    assert result['pages_scanned']==2
    assert result['issues_count']>0
    assert result['summary']['pages'][0]['url']=='https://example.com/'
    assert not any('other.example' in url for url in requested)


def test_robots_disallow_is_respected(monkeypatch):
    from app.services import seo_engine
    def fake_fetch(url,**kwargs):
        if url.endswith('/robots.txt'):
            return FetchResult(url,200,'text/plain','User-agent: *\nDisallow: /\n')
        raise AssertionError('Page must not be fetched after robots disallow')
    monkeypatch.setattr(seo_engine,'fetch_public_page',fake_fetch)
    from app.core.exceptions import ValidationError
    try:seo_engine.run_audit('https://example.com/')
    except ValidationError as exc:assert 'crawlable' in str(exc)
    else:raise AssertionError('robots disallow should prevent scanning')


def test_scan_fetch_failure_never_produces_seo_score(monkeypatch):
    from app.services import seo_engine
    def fake_fetch(url, **kwargs):
        if url.endswith('/robots.txt'):
            return FetchResult(url, 200, 'text/plain', 'User-agent: *\nAllow: /\n')
        raise ValidationError('Connection timed out. Check server availability.')
    monkeypatch.setattr(seo_engine, 'fetch_public_page', fake_fetch)
    result = seo_engine.run_audit('https://example.com/')
    assert result['status'] == 'failed'
    assert result['score'] == 0
    assert result['pages_scanned'] == 0
    assert result['summary']['attempted_pages'] == 1
    assert result['summary']['failed_pages'] == 1
    assert result['findings'][0]['rule'] == 'fetch_failed'


def test_partial_scan_scores_only_successfully_fetched_pages(monkeypatch):
    from app.services import seo_engine
    def fake_fetch(url, **kwargs):
        if url.endswith('/robots.txt'):
            return FetchResult(url, 200, 'text/plain', 'User-agent: *\nAllow: /\n')
        if url.endswith('/about'):
            raise ValidationError('Connection timed out.')
        return FetchResult(url, 200, 'text/html', '<html lang="en"><head><title>Home</title></head><body><h1>Welcome</h1><a href="/about">About</a></body></html>')
    monkeypatch.setattr(seo_engine, 'fetch_public_page', fake_fetch)
    result = seo_engine.run_audit('https://example.com/')
    assert result['status'] == 'partial'
    assert result['pages_scanned'] == 1
    assert result['summary']['attempted_pages'] == 2
    assert result['summary']['failed_pages'] == 1
    assert result['score'] < 100


def test_public_ip_fallback_uses_second_validated_address(monkeypatch):
    from app.services import seo_engine
    called = []
    class FakeConnection:
        def __init__(self, hostname, ip, **kwargs):
            called.append(ip)
            self.ip = ip
        def request(self, *args, **kwargs):
            if self.ip == '8.8.8.8':
                raise TimeoutError('No route')
        def getresponse(self):
            class Response:
                status = 200
                def getheaders(self): return [('Content-Type', 'text/html')]
                def read(self, max_bytes): return b'<html><title>OK</title></html>'
            return Response()
        def close(self): pass
    monkeypatch.setattr(seo_engine, 'public_addresses', lambda host: ['8.8.8.8', '1.1.1.1'])
    monkeypatch.setattr(seo_engine, '_PinnedHTTPS', FakeConnection)
    page = seo_engine.fetch_public_page('https://example.com/')
    assert page.status == 200
    assert called == ['8.8.8.8', '1.1.1.1']


def test_failed_audit_status_persists(client: TestClient, auth_headers: dict, monkeypatch):
    from app.api.v1.endpoints import intelligence
    from app.services import seo_engine
    def fake_fetch(url, **kwargs):
        if url.endswith('/robots.txt'):
            return FetchResult(url, 200, 'text/plain', 'User-agent: *\nAllow: /\n')
        raise ValidationError('TLS certificate verification failed.')
    monkeypatch.setattr(seo_engine, 'fetch_public_page', fake_fetch)
    org = client.get('/api/v1/organizations', headers=auth_headers).json()[0]['id']
    site = client.post(f'/api/v1/organizations/{org}/websites', json={'name':'Test','url':'https://example.com/'}, headers=auth_headers).json()
    response = client.post(f'/api/v1/websites/{site["id"]}/audits', headers=auth_headers)
    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'failed'
    assert response.json()['pages_scanned'] == 0
    assert response.json()['score'] is None
    detail = client.get(f'/api/v1/audits/{response.json()["id"]}', headers=auth_headers).json()
    assert detail['audit']['status'] == 'failed'
    assert detail['findings'][0]['rule'] == 'fetch_failed'


def test_legacy_invalid_scan_is_normalized_in_response():
    from app.api.v1.endpoints.intelligence import AuditRead
    from datetime import datetime, timezone
    import uuid
    legacy = AuditRead.model_validate({
        "id": uuid.uuid4(), "website_id": uuid.uuid4(), "created_at": datetime.now(timezone.utc),
        "score": 88, "pages_scanned": 1, "issues_count": 1, "status": "completed",
        "summary": {"pages": [{"url":"https://example.com/", "status":"error", "title":"", "issues":1}]}
    })
    assert legacy.status == "failed"
    assert legacy.score is None
    assert legacy.pages_scanned == 0
