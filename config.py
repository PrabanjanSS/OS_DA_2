import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    # Model for both grading and question generation. The free tier meters each
    # model separately, so switching this is the way out of a per-model cap.
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'models/gemini-2.5-flash')

    # Shared access code required to register a teacher account.
    # Leave empty to disable teacher self-registration entirely.
    TEACHER_SIGNUP_CODE = os.getenv('TEACHER_SIGNUP_CODE', '')

    # App-wide idle session timeout: a signed-in user is logged out after this
    # many minutes without a request. SESSION_REFRESH_EACH_REQUEST makes the
    # window slide on every request, so only inactivity ends the session.
    SESSION_TIMEOUT_MINUTES = int(os.getenv('SESSION_TIMEOUT_MINUTES', '30'))
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    SESSION_REFRESH_EACH_REQUEST = True
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///grading_system.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
    
    # Threading settings
    MAX_WORKERS = int(os.getenv('MAX_WORKERS', '4'))
    
    # Validation settings
    SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.1'))  # Lowered from 0.3 to 0.1
    MAX_SCORE = 10
