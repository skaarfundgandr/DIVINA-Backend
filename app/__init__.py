import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from config import config

db = SQLAlchemy()
bcrypt = Bcrypt()


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Upload folder config
    app.config.setdefault(
        "UPLOAD_FOLDER",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"),
    )
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    bcrypt.init_app(app)

    from app.routes.auth import auth_bp
    from app.routes.protected import protected_bp
    from app.routes.admin import admin_bp
    from app.routes.books import booking_bp
    from app.routes.store import store_bp
    from app.routes.coupon import admin_coupon_bp, coupon_bp
    from app.routes.weather import weather_bp
    from app.routes.identify import identify_bp
    
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(protected_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(booking_bp, url_prefix="/api/")
    app.register_blueprint(store_bp, url_prefix="/api")
    app.register_blueprint(coupon_bp, url_prefix="/api")
    app.register_blueprint(admin_coupon_bp, url_prefix="/api/admin")
    app.register_blueprint(weather_bp, url_prefix="/api")
    app.register_blueprint(identify_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()

    return app