import os
from flask import Flask, render_template
from sqlalchemy import inspect, text
from config import Config
from extensions import db, login_manager
from auth.routes import auth_bp
from teacher.routes import teacher_bp
from student.routes import student_bp


def ensure_schema():
    """Add newly introduced columns to an existing SQLite database."""
    inspector = inspect(db.engine)
    if 'logs' not in inspector.get_table_names():
        return
    columns = {col['name'] for col in inspector.get_columns('logs')}
    with db.engine.begin() as conn:
        if 'manually_graded' not in columns:
            conn.execute(text('ALTER TABLE logs ADD COLUMN manually_graded BOOLEAN DEFAULT 0'))
        if 'teacher_comment' not in columns:
            conn.execute(text('ALTER TABLE logs ADD COLUMN teacher_comment TEXT'))

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    
    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(teacher_bp, url_prefix='/teacher')
    app.register_blueprint(student_bp, url_prefix='/student')
    
    # Create database tables
    with app.app_context():
        db.create_all()
        ensure_schema()
    
    # Root route
    @app.route('/')
    def index():
        return render_template('index.html')
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, threaded=True, port=5002)
