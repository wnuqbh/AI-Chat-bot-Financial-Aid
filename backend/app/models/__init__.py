from datetime import datetime, timezone

from app import db


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(120))
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    account_locked = db.Column(db.Boolean, nullable=False, default=False)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    sessions = db.relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    portfolio = db.relationship("Portfolio", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "is_admin": self.is_admin,
            "account_locked": self.account_locked,
            "created_at": self.created_at.isoformat(),
        }


class ChatSession(db.Model):
    """A user's chat session. Named ChatSession to avoid confusion with SQLAlchemy's db.session."""

    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="sessions")
    conversations = db.relationship("Conversation", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "conversation_ids": [c.id for c in self.conversations],
        }


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    session = db.relationship("ChatSession", back_populates="conversations")
    messages = db.relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    role = db.Column(db.String(16), nullable=False)  # "user" or "assistant"
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    conversation = db.relationship("Conversation", back_populates="messages")

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }


class Portfolio(db.Model):
    __tablename__ = "portfolios"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False, default="My Portfolio")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="portfolio")
    holdings = db.relationship(
        "Holding", back_populates="portfolio", cascade="all, delete-orphan", order_by="Holding.symbol"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "holdings": [h.to_dict() for h in self.holdings],
        }


class Holding(db.Model):
    __tablename__ = "holdings"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id"), nullable=False, index=True)
    symbol = db.Column(db.String(16), nullable=False)
    quantity = db.Column(db.Numeric(18, 6), nullable=False)
    average_cost = db.Column(db.Numeric(18, 4), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    portfolio = db.relationship("Portfolio", back_populates="holdings")

    __table_args__ = (db.UniqueConstraint("portfolio_id", "symbol", name="uq_holding_symbol"),)

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "quantity": str(self.quantity),
            "average_cost": str(self.average_cost),
        }


class AuditLog(db.Model):
    """Kept independent of User (no relationship/cascade) so logs survive account deletion."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat(),
        }
