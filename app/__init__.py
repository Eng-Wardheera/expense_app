
import os
import traceback
from datetime import datetime

import pytz
import cloudinary
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, url_for, request
from flask_cors import CORS
from flask_login import LoginManager, current_user
from authlib.integrations.flask_client import OAuth

from app.extensions import mongo, mail
from app.tracker import init_tracker


load_dotenv()

# --------------------------------------------------
# Global configuration
# --------------------------------------------------

login_manager = LoginManager()
oauth = OAuth()

google = None
github = None

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
UPLOAD_FOLDER = "static/backend/uploads"
MAX_RETRIES = 5

EAT = pytz.timezone("Africa/Nairobi")


def now_eat():
    return datetime.now(EAT)


# --------------------------------------------------
# Cloudinary configuration
# --------------------------------------------------

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


# --------------------------------------------------
# Create Flask application
# --------------------------------------------------

def create_app():

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )

    # --------------------------------------------------
    # Security
    # --------------------------------------------------

    secret_key = os.getenv("SECRET_KEY")

    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is missing")

    app.config["SECRET_KEY"] = secret_key

    app.config["DEBUG"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False

    # --------------------------------------------------
    # MongoDB
    # --------------------------------------------------

    mongo_uri = os.getenv("MONGO_URI")

    if not mongo_uri:
        raise RuntimeError("MONGO_URI environment variable is missing")

    app.config["MONGO_URI"] = mongo_uri
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

    mongo.init_app(app)

    # --------------------------------------------------
    # Flask Mail
    # Initialize only once
    # --------------------------------------------------

    app.config.update(
        MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
        MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "True").lower() == "true",
        MAIL_USE_SSL=os.getenv("MAIL_USE_SSL", "False").lower() == "true",
        MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=(
            os.getenv("MAIL_DEFAULT_SENDER")
            or os.getenv("MAIL_USERNAME")
        ),
        PUBLIC_BASE_URL=os.getenv("APP_BASE_URL", "").rstrip("/")
    )

    mail.init_app(app)

    # --------------------------------------------------
    # CORS
    # --------------------------------------------------

    port = int(os.getenv("PORT", 7000))

    frontend_origin = os.getenv(
        "FRONTEND_ORIGIN",
        f"http://127.0.0.1:{port}"
    )

    CORS(
        app,
        resources={
            r"/*": {
                "origins": frontend_origin
            }
        }
    )

    # --------------------------------------------------
    # OAuth
    # --------------------------------------------------

    oauth.init_app(app)

    global google, github

    google = oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        server_metadata_url=(
            "https://accounts.google.com/"
            ".well-known/openid-configuration"
        ),
        client_kwargs={
            "scope": "openid email profile"
        }
    )

    github = oauth.register(
        name="github",
        client_id=os.getenv("GITHUB_CLIENT_ID"),
        client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={
            "scope": "user:email"
        }
    )

    # --------------------------------------------------
    # Tracker
    # --------------------------------------------------

    init_tracker(app, mongo)

    # --------------------------------------------------
    # Login Manager
    # --------------------------------------------------

    login_manager.init_app(app)
    login_manager.login_view = "main.login"

    # --------------------------------------------------
    # Template filters
    # --------------------------------------------------

    @app.template_filter("getattr")
    def getattr_filter(obj, name):
        return getattr(obj, name, None)

    @app.template_filter("datetimeformat_input")
    def datetimeformat_input(value):
        if not value:
            return ""

        return value.strftime("%Y-%m-%dT%H:%M")

    @app.template_filter("datetimeformat_input_dateOnly")
    def datetimeformat_input_dateOnly(value):
        if not value:
            return ""

        return value.strftime("%Y-%m-%d")

    @app.template_filter("time_since")
    def time_since_filter(seconds):

        seconds = int(seconds or 0)

        intervals = (
            ("month", 2592000),
            ("week", 604800),
            ("day", 86400),
            ("hour", 3600),
            ("minute", 60),
            ("second", 1),
        )

        for name, count in intervals:
            value = seconds // count

            if value:
                return (
                    f"{value} {name}"
                    f"{'s' if value > 1 else ''} ago"
                )

        return "just now"

    # --------------------------------------------------
    # Context processors
    # --------------------------------------------------

    @app.context_processor
    def inject_year():
        return {
            "current_year": datetime.now().year
        }

    @app.context_processor
    def inject_settings():
        settings = mongo.db.settings.find_one()

        return {
            "settings": settings
        }

    # --------------------------------------------------
    # Register main blueprint
    # --------------------------------------------------

    from app.routes import bp

    app.register_blueprint(bp)

    # --------------------------------------------------
    # User model
    # --------------------------------------------------

    from app.modal import User

    @login_manager.user_loader
    def load_user(user_id):

        from bson.objectid import ObjectId
        from bson.errors import InvalidId

        try:
            user_data = mongo.db.users.find_one({
                "_id": ObjectId(user_id)
            })

            if user_data:
                return User(user_data)

        except (InvalidId, TypeError, ValueError):
            return None

        return None

    # --------------------------------------------------
    # Personal Timeline
    # --------------------------------------------------

    from app.personal_plan import create_personal_plan_blueprint

    app.register_blueprint(
        create_personal_plan_blueprint(mongo)
    )

    # --------------------------------------------------
    # Personal Plan Notifications
    # --------------------------------------------------

    from app.plan_notifications import (
        create_plan_notifications_blueprint
    )

    app.register_blueprint(
        create_plan_notifications_blueprint(mongo)
    )

    # --------------------------------------------------
    # 404 Error Handler
    # --------------------------------------------------

    @app.errorhandler(404)
    def not_found_error(error):

        site_settings = mongo.db.settings.find_one()

        return render_template(
            "backend/errors/auth-404-creative.html",
            settings=site_settings
        ), 404

    # --------------------------------------------------
    # 500 Error Handler
    # --------------------------------------------------

    @app.errorhandler(500)
    def internal_error(error):

        current_time = datetime.now(EAT).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        request_url = request.url

        user_info = (
            current_user.username
            if current_user.is_authenticated
            else "Guest"
        )

        error_message = str(error)

        error_trace = (
            traceback.format_exc()
            if app.debug
            else None
        )

        site_settings = mongo.db.settings.find_one()

        return render_template(
            "backend/errors/auth-500-creative.html",
            settings=site_settings,
            time=current_time,
            user=user_info,
            url=request_url,
            message=error_message,
            trace=error_trace,
            debug=app.debug
        ), 500

    # --------------------------------------------------
    # Unauthorized Handler
    # --------------------------------------------------

    @login_manager.unauthorized_handler
    def unauthorized():

        flash("Fadlan marka hore soo gal nidaamka.")

        return redirect(
            url_for("main.login")
        )

    return app
