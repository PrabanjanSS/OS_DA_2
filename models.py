from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'teacher' or 'student'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    sets = db.relationship('Set', backref='teacher', lazy=True)
    access_grants = db.relationship('AccessGrant', backref='student', lazy=True)
    logs = db.relationship('Log', backref='student', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Set(db.Model):
    __tablename__ = 'sets'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    materials = db.relationship('Material', backref='set', lazy=True, cascade='all, delete-orphan')
    questions = db.relationship('Question', backref='set', lazy=True, cascade='all, delete-orphan')
    access_grants = db.relationship('AccessGrant', backref='set', lazy=True, cascade='all, delete-orphan')

class Material(db.Model):
    __tablename__ = 'materials'
    
    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))  # pdf, docx, txt
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_text = db.Column(db.Text)  # Store extracted text for TF-IDF

class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    ideal_answer = db.Column(db.Text)  # Optional reference answer
    max_score = db.Column(db.Integer, default=10)
    
    # Relationships
    logs = db.relationship('Log', backref='question', lazy=True)

class AccessGrant(db.Model):
    __tablename__ = 'access_grants'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    max_attempts = db.Column(db.Integer, default=1)
    attempts_used = db.Column(db.Integer, default=0)
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('student_id', 'set_id', name='unique_student_set'),)

class Log(db.Model):
    __tablename__ = 'logs'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text)
    score = db.Column(db.Float)
    max_score = db.Column(db.Integer, default=10)
    source_used = db.Column(db.String(50))  # 'material_match', 'ai_api', 'fallback_dataset'
    confidence = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
