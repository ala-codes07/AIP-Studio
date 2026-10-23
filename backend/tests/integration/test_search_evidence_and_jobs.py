"""Final-release regression tests. External internet and SMTP are never used."""
import io
import uuid
from app.models.scan_job import ScanJob
from app.models.search_performance import SearchPerformanceImport
from app.services.search_console import parse_queries_csv, opportunities
from app.services.seo_engine import FetchResult, analyze_html
from app.services import scan_queue
from sqlalchemy import select

CSV=b'Query,Clicks,Impressions,CTR,Position\nmicrocement,4,240,1.67%,8.7\nwall paint,9,130,6.92%,15.4\n'


def create_site(client, auth_headers):
    org=client.get('/api/v1/organizations',headers=auth_headers).json()[0]['id']
    resp=client.post(f'/api/v1/organizations/{org}/websites',headers=auth_headers,json={
        'name':'Test Public Site','url':'https://example.com/'})
    assert resp.status_code==201,resp.text
    return resp.json()


def test_parse_csv_real_metrics_and_priorities():
    data=parse_queries_csv(CSV)
    assert data['total_impressions']==370
    assert data['total_clicks']==13
    assert data['rows'][0]['ctr']==0.0167
    op=opportunities(data['rows'])
    assert op[0]['query']=='microcement'
    assert 'estimated' not in str(op).lower()


def test_reject_invalid_csv_and_csv_formula_rows():
    from app.core.exceptions import ValidationError
    bad=[b'Query,Clicks\ntest,10\n',
         b'Query,Clicks,Impressions,CTR,Position\n=test(),2,10,20%,3\n',
         b'Query,Clicks,Impressions,CTR,Position\nword,11,10,20%,3\n',
         b'Query,Clicks,Impressions,CTR,Position\nword,1,10,20%,NaN\n',
         b'Query,Clicks,Impressions,CTR,Position\nword,1,10,20%,3\nword,2,20,10%,4\n']
    for item in bad:
        try:parse_queries_csv(item)
        except ValidationError:pass
        else:raise AssertionError('Invalid CSV accepted')


def test_import_and_access_control(client,auth_headers,sent_codes):
    site=create_site(client,auth_headers)
    path=f'/api/v1/websites/{site["id"]}/search-console'
    result=client.post(path+'/import',headers=auth_headers,files={'file':('queries.csv',CSV,'text/csv')})
    assert result.status_code==201,result.text
    assert result.json()['row_count']==2
    assert result.json()['total_clicks']==13
    assert result.json()['opportunities']
    assert client.get(path,headers=auth_headers).json()['row_count']==2
    client.post('/api/v1/auth/register',json={'email':'othergsc@example.com','password':'TestPassword123'})
    client.post('/api/v1/auth/verify-email',json={'email':'othergsc@example.com','code':sent_codes[('othergsc@example.com','verify')]})
    auth=client.post('/api/v1/auth/login',data={'username':'othergsc@example.com','password':'TestPassword123'}).json()
    outsider={'Authorization':'Bearer '+auth['access_token']}
    assert client.get(path,headers=outsider).status_code==404
    assert client.post(path+'/import',headers=outsider,files={'file':('q.csv',CSV,'text/csv')}).status_code==404


def test_queue_worker_persists_report(client,auth_headers,db,monkeypatch):
    site=create_site(client,auth_headers)
    path=f'/api/v1/websites/{site["id"]}/jobs'
    created=client.post(path,headers=auth_headers)
    assert created.status_code==202,created.text
    job=created.json()
    assert job['status']=='queued'
    assert client.post(path,headers=auth_headers).status_code==429
    def fake(url):
        page=FetchResult(url,200,'text/html','<html lang="en"><head><title>Demo site</title></head><body><h1>Demo site</h1><p>Useful content.</p></body></html>')
        issues,_=analyze_html(page)
        return {'score':90,'status':'completed','pages_scanned':1,'issues_count':len(issues),
                'summary':{'pages':[{'url':url,'status':200,'title':'Demo site','issues':len(issues)}],
                           'content_analysis':{'pages':[{'url':url,'title':'Demo site','h1':['Demo site'],'keywords':[]}],
                                               'keywords':[],'recommendations':[]}},'findings':issues}
    monkeypatch.setattr(scan_queue,'run_audit',fake)
    assert scan_queue.process_one(db)
    response=client.get(path+'/'+job['id'],headers=auth_headers)
    assert response.status_code==200,response.text
    assert response.json()['status']=='completed'
    assert response.json()['audit_id']
    report=client.get('/api/v1/audits/'+response.json()['audit_id'],headers=auth_headers)
    assert report.status_code==200
    assert report.json()['audit']['pages_scanned']==1
    assert scan_queue.process_one(db) is False


def test_worker_failure_is_recorded(client,auth_headers,db,monkeypatch):
    site=create_site(client,auth_headers)
    path=f'/api/v1/websites/{site["id"]}/jobs'
    job=client.post(path,headers=auth_headers).json()
    def fail(url):
        from app.core.exceptions import ValidationError
        raise ValidationError('The website refused the scan.')
    monkeypatch.setattr(scan_queue,'run_audit',fail)
    assert scan_queue.process_one(db)
    row=client.get(path+'/'+job['id'],headers=auth_headers).json()
    assert row['status']=='failed'
    assert row['audit_id'] is None
    assert 'refused' in row['error']
    assert client.post(path,headers=auth_headers).status_code==202


def test_structured_data_checks_and_og_headers():
    page=FetchResult('https://example.com/',200,'text/html',
        '<html lang="fa"><head><title>میکروسمنت کف</title><script type="application/ld+json">{"@type":"Product"}</script></head><body><h1>میکروسمنت کف</h1></body></html>',
        headers={'x-robots-tag':'noindex'},response_ms=1540)
    findings,parsed=analyze_html(page)
    assert 'Product' in parsed.schema_types
    rules={f['rule'] for f in findings}
    assert {'xrobots_noindex','slow_response','social_preview'} <= rules
