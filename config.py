import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

    # Shared access code required to register a teacher account.
    # Leave empty to disable teacher self-registration entirely.
    TEACHER_SIGNUP_CODE = os.getenv('TEACHER_SIGNUP_CODE', '')
    
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
