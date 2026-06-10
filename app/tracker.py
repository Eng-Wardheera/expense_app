from flask import request, session
from datetime import datetime

def init_tracker(app, mongo):

    @app.before_request
    def track_route():

        if request.path.startswith("/static"):
            return

        token = session.get("guest_token")

        if not token:
            from app.routes import create_guest_session
            create_guest_session(mongo)
            token = session.get("guest_token")

        mongo.db.sessions.update_one(
            {"session_token": token},
            {
                "$push": {
                    "routes": {
                        "path": request.path,
                        "time": datetime.utcnow()
                    }
                }
            }
        )
