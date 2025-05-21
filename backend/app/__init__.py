# backend/app/__init__.py
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables

def create_app():
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes
    
    # Configure app
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this')
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.chat import chat_bp
    from app.routes.mood import mood_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(mood_bp, url_prefix='/api/mood')
    
    return app



