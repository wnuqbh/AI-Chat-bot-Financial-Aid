import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    from flask_migrate import upgrade

    # Dev convenience: bring the local database up to date on every start.
    # In production, migrations run once before the server starts (see docker-entrypoint.sh).
    with app.app_context():
        upgrade()

    # Localhost only by default: the debug server's interactive debugger must not be reachable from the network.
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")))
