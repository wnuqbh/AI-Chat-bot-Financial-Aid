from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import db
from app.middleware import current_user_id
from app.models import Holding, Portfolio
from app.schemas import HoldingSchema
from app.services.audit import record_audit

portfolio_bp = Blueprint("portfolio", __name__)


def _get_or_create_portfolio(user_id):
    portfolio = Portfolio.query.filter_by(user_id=user_id).first()
    if portfolio is None:
        portfolio = Portfolio(user_id=user_id)
        db.session.add(portfolio)
        db.session.flush()
    return portfolio


def _get_owned_holding(holding_id, user_id):
    return db.first_or_404(
        db.select(Holding).join(Portfolio).filter(Holding.id == holding_id, Portfolio.user_id == user_id),
        description="Holding not found",
    )


@portfolio_bp.get("/")
@jwt_required()
def get_portfolio():
    portfolio = _get_or_create_portfolio(current_user_id())
    db.session.commit()
    return jsonify({"portfolio": portfolio.to_dict()})


@portfolio_bp.post("/holding")
@jwt_required()
def add_holding():
    data = HoldingSchema().load(request.get_json(silent=True) or {})
    user_id = current_user_id()
    portfolio = _get_or_create_portfolio(user_id)
    symbol = data["symbol"].upper()

    if Holding.query.filter_by(portfolio_id=portfolio.id, symbol=symbol).first():
        return jsonify({"error": f"{symbol} is already in the portfolio; update it instead"}), 409

    holding = Holding(portfolio=portfolio, symbol=symbol, quantity=data["quantity"], average_cost=data["average_cost"])
    db.session.add(holding)
    record_audit("holding_added", user_id=user_id, details=symbol)
    db.session.commit()
    return jsonify({"holding": holding.to_dict()}), 201


@portfolio_bp.put("/holding/<int:holding_id>")
@jwt_required()
def update_holding(holding_id):
    data = HoldingSchema(only=("quantity", "average_cost")).load(request.get_json(silent=True) or {})
    user_id = current_user_id()
    holding = _get_owned_holding(holding_id, user_id)
    holding.quantity = data["quantity"]
    holding.average_cost = data["average_cost"]
    record_audit("holding_updated", user_id=user_id, details=holding.symbol)
    db.session.commit()
    return jsonify({"holding": holding.to_dict()})


@portfolio_bp.delete("/holding/<int:holding_id>")
@jwt_required()
def delete_holding(holding_id):
    user_id = current_user_id()
    holding = _get_owned_holding(holding_id, user_id)
    record_audit("holding_deleted", user_id=user_id, details=holding.symbol)
    db.session.delete(holding)
    db.session.commit()
    return "", 204
