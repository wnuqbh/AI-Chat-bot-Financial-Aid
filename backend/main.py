import os

from app import create_app, db

app = create_app(os.getenv("FLASK_ENV", "development"))

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    # Localhost only by default: the debug server's interactive debugger must not be reachable from the network.
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")))
