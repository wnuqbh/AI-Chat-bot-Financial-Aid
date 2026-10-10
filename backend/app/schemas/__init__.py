from marshmallow import Schema, fields, validate


class RegisterSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=8, max=128))
    full_name = fields.String(validate=validate.Length(max=120))


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True)


class CreateSessionSchema(Schema):
    title = fields.String(validate=validate.Length(max=200))


class MessageSchema(Schema):
    conversation_id = fields.Integer(required=True)
    content = fields.String(required=True, validate=validate.Length(min=1, max=4000))


class HoldingSchema(Schema):
    symbol = fields.String(required=True, validate=validate.Regexp(r"^[A-Za-z.\-]{1,16}$"))
    quantity = fields.Decimal(required=True, validate=validate.Range(min=0, min_inclusive=False))
    average_cost = fields.Decimal(required=True, validate=validate.Range(min=0))
