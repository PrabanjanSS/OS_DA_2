import os
from flask import Flask, render_template
from sqlalchemy import inspect, text
from config import Config
from extensions import db, login_manager
from auth.routes import auth_bp
from teacher.routes import teacher_bp
from student.routes import student_bp


# Columns added after the initial release: table -> column -> column definition.
# Applied on startup so existing SQLite databases keep working without a reset.
NEW_COLUMNS = {
    'logs': {
        'manually_graded': 'BOOLEAN DEFAULT 0',
        'teacher_comment': 'TEXT',
        'submitted_late': 'BOOLEAN DEFAULT 0',
        'attempt_no': 'INTEGER DEFAULT 1',
        'key_point': 'TEXT',
        'submission_id': 'INTEGER',
    },
    'questions': {
        'strictness': 'INTEGER DEFAULT 3',
        'is_generated': 'BOOLEAN DEFAULT 0',
        'topic': 'TEXT',
        'difficulty': 'INTEGER',
    },
    'sets': {
        'book_mode': "TEXT DEFAULT 'open_book'",
        'time_limit_minutes': 'INTEGER',
        'is_pool_based': 'BOOLEAN DEFAULT 0',
        'questions_per_student': 'INTEGER',
        'pool_topic': 'TEXT',
        'pool_difficulty': 'INTEGER',
        'pool_notes': 'TEXT',
        'delivery_mode': "TEXT DEFAULT 'quiz'",
        'due_at': 'DATETIME',
        'submissions_close_at': 'DATETIME',
        'pool_kind': 'TEXT',
    },
    'materials': {
        'kind': "TEXT DEFAULT 'material'",
        'is_generated': 'BOOLEAN DEFAULT 0',
    },
    'access_grants': {
        'attempt_started_at': 'DATETIME',
        'attempt_deadline': 'DATETIME',
        'class_group_id': 'INTEGER',
    },
}


def ensure_schema():
    """Add newly introduced columns to an existing SQLite database."""
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    with db.engine.begin() as conn:
        for table, columns in NEW_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col['name'] for col in inspector.get_columns(table)}
            for column, definition in columns.items():
                if column not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {definition}'))

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
        # Always the landing page: starting the server lands here even if the
        # browser still holds a session from a previous run. Signed-in users
        # reach their dashboard from the navbar link instead.
        return render_template('index.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, threaded=True, port=5002)
