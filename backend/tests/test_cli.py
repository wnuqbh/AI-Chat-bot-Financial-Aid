from app import db
from app.models import User


def test_make_admin_command(app, register):
    user_id, _ = register(email="boss@example.com")
    runner = app.test_cli_runner()

    result = runner.invoke(args=["make-admin", "Boss@example.com"])
    assert result.exit_code == 0, result.output
    assert db.session.get(User, user_id).is_admin

    runner.invoke(args=["make-admin", "boss@example.com", "--revoke"])
    db.session.expire_all()
    assert not db.session.get(User, user_id).is_admin

    assert runner.invoke(args=["make-admin", "nobody@example.com"]).exit_code != 0
