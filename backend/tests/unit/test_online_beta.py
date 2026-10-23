"""Cloud adapter regression checks, no outbound network or real credentials."""
from __future__ import annotations
from threading import Event
import pytest


def test_cloud_postgres_url_normalization():
    from app.db.session import normalized_database_url
    assert normalized_database_url('postgres://u:p@host/db?sslmode=require') == 'postgresql+psycopg://u:p@host/db?sslmode=require'
    assert normalized_database_url('postgresql://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
    assert normalized_database_url('postgresql+psycopg://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
    assert normalized_database_url('sqlite+pysqlite:///./platform.db') == 'sqlite+pysqlite:///./platform.db'


def test_invite_only_case_and_spaces():
    from app.api.v1.endpoints.auth import registration_invited
    assert registration_invited('  EXAMPLE@GMAIL.COM ', 'other@example.com, example@gmail.com')
    assert not registration_invited('someone@example.com', 'other@example.com,example@gmail.com')
    assert not registration_invited('x@example.com', '')


def test_brevo_https_delivery_does_not_use_smtp(monkeypatch):
    from app.services import email_codes
    from types import SimpleNamespace
    seen = {}

    class Response:
        def raise_for_status(self):
            seen['success'] = True

    class Client:
        def __init__(self, **kwargs):
            seen['timeout'] = kwargs.get('timeout')
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, **kwargs):
            seen['url'] = url
            seen['kwargs'] = kwargs
            return Response()

    monkeypatch.setattr(email_codes, 'get_settings', lambda: SimpleNamespace(
        EMAIL_MODE='brevo', BREVO_API_KEY='private-test-only', SMTP_FROM='beta@example.com',
        is_production=True))
    monkeypatch.setattr(email_codes.httpx, 'Client', Client)
    email_codes.deliver_code('recipient@example.com', 'reset', '654321')
    assert seen['success'] is True
    assert seen['url'] == 'https://api.brevo.com/v3/smtp/email'
    assert seen['kwargs']['json']['to'] == [{'email': 'recipient@example.com'}]
    assert '654321' in seen['kwargs']['json']['textContent']
    assert seen['kwargs']['headers']['api-key'] == 'private-test-only'


def test_worker_can_quit_when_stopped():
    from app.scripts.scan_worker import run_worker
    stop = Event()
    stop.set()
    run_worker(stop_event=stop)


def test_cloud_start_validates_port_before_process(monkeypatch):
    from app.scripts import start_cloud
    called = []
    monkeypatch.setattr(start_cloud, 'migrate', lambda: called.append('schema'))
    monkeypatch.setenv('PORT', 'oops')
    with pytest.raises(RuntimeError, match='PORT'):
        start_cloud.main()
    assert called == ['schema']
