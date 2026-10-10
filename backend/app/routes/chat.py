import json

from flask import Blueprint, Response, abort, current_app, jsonify, request, stream_with_context
from flask_jwt_extended import jwt_required

from app import db, limiter
from app.middleware import chat_rate_limit, current_user_id, user_rate_limit_key
from app.models import ChatSession, Conversation, Message
from app.schemas import CreateSessionSchema, MessageSchema
from app.services.advisor import AdvisorUnavailableError, generate_reply, stream_reply

chat_bp = Blueprint("chat", __name__)


def _get_owned_conversation(conversation_id, user_id):
    # Join through the session so users can only reach their own conversations.
    conversation = (
        Conversation.query.join(ChatSession)
        .filter(Conversation.id == conversation_id, ChatSession.user_id == user_id)
        .first()
    )
    if conversation is None:
        abort(404, description="Conversation not found")
    return conversation


def _start_exchange():
    """Validate the request and stage the user's message (uncommitted) in its conversation."""
    data = MessageSchema().load(request.get_json(silent=True) or {})
    conversation = _get_owned_conversation(data["conversation_id"], current_user_id())
    user_message = Message(conversation=conversation, role="user", content=data["content"])
    db.session.add(user_message)
    return conversation, user_message


def _finish_exchange(conversation, user_message, reply):
    """Save the reply alongside the user's message; both are committed together or not at all."""
    assistant_message = Message(conversation=conversation, role="assistant", content=reply)
    db.session.add(assistant_message)
    if not conversation.session.title:
        conversation.session.title = user_message.content[:60]
    db.session.commit()
    return {"user_message": user_message.to_dict(), "assistant_message": assistant_message.to_dict()}


@chat_bp.post("/session")
@jwt_required()
def create_session():
    data = CreateSessionSchema().load(request.get_json(silent=True) or {})
    session = ChatSession(user_id=current_user_id(), title=data.get("title"))
    conversation = Conversation(session=session)
    db.session.add_all([session, conversation])
    db.session.commit()
    return jsonify({"session": session.to_dict(), "conversation_id": conversation.id}), 201


@chat_bp.get("/sessions")
@jwt_required()
def list_sessions():
    sessions = (
        ChatSession.query.filter_by(user_id=current_user_id()).order_by(ChatSession.created_at.desc()).all()
    )
    return jsonify({"sessions": [s.to_dict() for s in sessions]})


@chat_bp.post("/message")
@jwt_required()
@limiter.limit(chat_rate_limit, key_func=user_rate_limit_key)
def send_message():
    conversation, user_message = _start_exchange()
    try:
        reply = generate_reply(conversation.messages, conversation.session.user.portfolio)
    except AdvisorUnavailableError as err:
        db.session.rollback()
        return jsonify({"error": str(err)}), 503
    return jsonify(_finish_exchange(conversation, user_message, reply)), 201


def _sse(event):
    return f"data: {json.dumps(event)}\n\n"


@chat_bp.post("/message/stream")
@jwt_required()
@limiter.limit(chat_rate_limit, key_func=user_rate_limit_key)
def stream_message():
    """Like /message, but streams the reply as Server-Sent Events.

    Events: {"type": "delta", "text"} for each chunk, then {"type": "done", "user_message", "assistant_message"}
    once both messages are saved, or {"type": "error", "error"} (nothing is saved in that case).
    """
    conversation, user_message = _start_exchange()
    history = list(conversation.messages)
    portfolio = conversation.session.user.portfolio

    @stream_with_context
    def events():
        parts = []
        try:
            for text in stream_reply(history, portfolio):
                parts.append(text)
                yield _sse({"type": "delta", "text": text})
            yield _sse({"type": "done", **_finish_exchange(conversation, user_message, "".join(parts))})
        except AdvisorUnavailableError as err:
            db.session.rollback()
            yield _sse({"type": "error", "error": str(err)})
        except Exception:
            # Headers are already sent, so the global error handler can't respond; report in-stream instead.
            current_app.logger.exception("Error while streaming a reply")
            db.session.rollback()
            yield _sse({"type": "error", "error": "Internal server error"})

    return Response(
        events(),
        mimetype="text/event-stream",
        # X-Accel-Buffering stops nginx from buffering the stream into one late chunk.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@chat_bp.get("/history/<int:conversation_id>")
@jwt_required()
def history(conversation_id):
    conversation = _get_owned_conversation(conversation_id, current_user_id())
    return jsonify({"conversation_id": conversation.id, "messages": [m.to_dict() for m in conversation.messages]})


@chat_bp.delete("/session/<int:session_id>")
@jwt_required()
def delete_session(session_id):
    session = db.first_or_404(
        db.select(ChatSession).filter_by(id=session_id, user_id=current_user_id()),
        description="Session not found",
    )
    db.session.delete(session)
    db.session.commit()
    return "", 204
