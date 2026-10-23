"""Import every model so Alembic's autogenerate sees the full metadata."""

from app.db.base import Base
from app.models.audit_log import AuditLog
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.models.auth_session import RefreshSession
from app.models.email_challenge import EmailChallenge
from app.models.intelligence import Website, WebsiteAudit, AuditFinding
from app.models.search_performance import SearchPerformanceImport
from app.models.scan_job import ScanJob

__all__ = [
    "Base",
    "AuditLog",
    "Organization",
    "OrganizationMember",
    "User",
    "Website",
    "WebsiteAudit",
    "AuditFinding",
    "RefreshSession",
    "EmailChallenge",
    "SearchPerformanceImport",
    "ScanJob",
]