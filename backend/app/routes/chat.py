from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app import db
from app.middleware import current_user_id
from app.models import ChatSession, Conversation, Message
from app.schemas import CreateSessionSchema, MessageSchema
from app.services.advisor import AdvisorUnavailableError, generate_reply

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
def send_message():
    data = MessageSchema().load(request.get_json(silent=True) or {})
    user_id = current_user_id()
    conversation = _get_owned_conversation(data["conversation_id"], user_id)

    user_message = Message(conversation=conversation, role="user", content=data["content"])
    db.session.add(user_message)

    try:
        reply = generate_reply(conversation.messages, conversation.session.user.portfolio)
    except AdvisorUnavailableError as err:
        db.session.rollback()
        return jsonify({"error": str(err)}), 503

    assistant_message = Message(conversation=conversation, role="assistant", content=reply)
    db.session.add(assistant_message)
    if not conversation.session.title:
        conversation.session.title = data["content"][:60]
    db.session.commit()
    return jsonify({"user_message": user_message.to_dict(), "assistant_message": assistant_message.to_dict()}), 201


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
