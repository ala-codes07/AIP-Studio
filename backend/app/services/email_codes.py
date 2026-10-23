"""Six-digit, single-use codes for email verification and password recovery.

The SMTP branch really sends email. The console transport intentionally works
only in development/test and NEVER returns the code in the HTTP response.
"""
from __future__ import annotations
import hashlib
import hmac
import logging
import secrets
import smtplib
import httpx
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.exceptions import ValidationError, RateLimitError
from app.models.email_challenge import EmailChallenge
from app.models.user import User

logger = logging.getLogger(__name__)
PURPOSES = {'verify', 'reset'}
EXPIRY_MINUTES = 10
RESEND_SECONDS = 60
MAX_ATTEMPTS = 5


def now_utc():
    return datetime.now(timezone.utc)


def aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def code_digest(user: User, purpose: str, code: str) -> str:
    key = get_settings().SECRET_KEY.encode()
    message = f'{user.id}:{purpose}:{code}'.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def deliver_code(to_email: str, purpose: str, code: str) -> None:
    settings = get_settings()
    if settings.EMAIL_MODE == 'console':
        if settings.is_production:
            raise RuntimeError('Console verification codes cannot be used in production. Configure SMTP.')
        # Only on local server stdout, never in response, telemetry, or git.
        print(f'\n[AIP LOCAL EMAIL] To: {to_email} | {purpose} code: {code} (valid 10 minutes)\n', flush=True)
        return
    if settings.EMAIL_MODE == 'brevo':
        if not settings.BREVO_API_KEY or not settings.SMTP_FROM:
            raise RuntimeError('HTTPS email requires BREVO_API_KEY and SMTP_FROM.')
        subject = ('AIP Studio — Verify your email' if purpose == 'verify'
                   else 'AIP Studio — Reset your password')
        body = (
            f'Your AIP Studio {"verification" if purpose == "verify" else "password reset"} code is: {code}\n'
            f'It expires in {EXPIRY_MINUTES} minutes. If you did not request this, ignore this email.\n'
        )
        # HTTPS/443 works on free platforms that block outgoing SMTP. Never log
        # credentials or OTPs. Sender must be approved in the Brevo account.
        with httpx.Client(timeout=15.0, trust_env=True) as client:
            response = client.post(
                'https://api.brevo.com/v3/smtp/email',
                headers={'api-key': settings.BREVO_API_KEY,
                         'accept': 'application/json', 'content-type': 'application/json'},
                json={'sender': {'email': settings.SMTP_FROM, 'name': 'AIP Studio'},
                      'to': [{'email': to_email}], 'subject': subject, 'textContent': body},
            )
            response.raise_for_status()
        return
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise RuntimeError('SMTP_HOST and SMTP_FROM must be configured to deliver email.')
    msg = EmailMessage()
    msg['From'] = settings.SMTP_FROM
    msg['To'] = to_email
    msg['Subject'] = 'AIP Studio — Verify your email' if purpose == 'verify' else 'AIP Studio — Reset your password'
    msg.set_content(
        f'Your AIP Studio {"verification" if purpose == "verify" else "password reset"} code is: {code}\n'
        f'It expires in {EXPIRY_MINUTES} minutes. If you did not request this, ignore this email.\n'
    )
    connection = smtplib.SMTP_SSL if settings.SMTP_SECURITY == 'ssl' else smtplib.SMTP
    with connection(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_SECURITY == 'starttls':
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


class EmailCodeService:
    def __init__(self, db: Session):
        self.db = db

    def send(self, user: User, purpose: str) -> None:
        assert purpose in PURPOSES
        current = now_utc()
        recent = self.db.scalar(select(EmailChallenge).where(
            EmailChallenge.user_id == user.id, EmailChallenge.purpose == purpose,
            EmailChallenge.consumed_at.is_(None)
        ).order_by(EmailChallenge.created_at.desc()).limit(1))
        if recent and (current - aware(recent.created_at)).total_seconds() < RESEND_SECONDS:
            raise RateLimitError('Please wait one minute before requesting another code.')
        code = f'{secrets.randbelow(1_000_000):06d}'
        while recent and code_digest(user, purpose, code) == recent.code_digest:
            code = f'{secrets.randbelow(1_000_000):06d}'
        try:
            deliver_code(user.email, purpose, code)  # fails closed if SMTP unavailable
        except (RuntimeError, OSError, smtplib.SMTPException, httpx.HTTPError) as exc:
            logger.exception('email_delivery_failed: purpose=%s', purpose)
            raise ValidationError('Email delivery is temporarily unavailable. Please try again later.') from exc
        self.db.execute(update(EmailChallenge).where(
            EmailChallenge.user_id == user.id, EmailChallenge.purpose == purpose,
            EmailChallenge.consumed_at.is_(None)
        ).values(consumed_at=current))
        self.db.add(EmailChallenge(
            user_id=user.id, purpose=purpose, code_digest=code_digest(user, purpose, code),
            expires_at=current + timedelta(minutes=EXPIRY_MINUTES),
            created_at=current, attempts=0,
        ))
        self.db.commit()

    def consume(self, user: User, purpose: str, code: str) -> None:
        challenge = self.db.scalar(select(EmailChallenge).where(
            EmailChallenge.user_id == user.id, EmailChallenge.purpose == purpose,
            EmailChallenge.consumed_at.is_(None)
        ).order_by(EmailChallenge.created_at.desc()).limit(1))
        if challenge is None or aware(challenge.expires_at) <= now_utc() or challenge.attempts >= MAX_ATTEMPTS:
            raise ValidationError('Code expired or unavailable. Request a new code.')
        challenge.attempts += 1
        # Persist failure count even if the caller catches the error.
        valid = hmac.compare_digest(challenge.code_digest, code_digest(user, purpose, code))
        if not valid:
            self.db.commit()
            raise ValidationError('Invalid code. Check your email and try again.')
        challenge.consumed_at = now_utc()
        # Do not commit here: owner transaction atomically applies verified/reset state.
