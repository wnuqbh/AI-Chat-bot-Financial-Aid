from flask import request

from app import db
from app.models import AuditLog


def record_audit(action, user_id=None, details=None):
    """Add an audit entry to the current transaction; the caller commits."""
    db.session.add(AuditLog(user_id=user_id, action=action, details=details, ip_address=request.remote_addr))
