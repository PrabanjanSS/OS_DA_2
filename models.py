from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

# A student can sit in more than one class (e.g. an OS slot for one subject and
# a different slot for another), so membership is many-to-many.
class_group_members = db.Table(
    'class_group_members',
    db.Column('class_group_id', db.Integer, db.ForeignKey('class_groups.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
)


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


class ClassGroup(db.Model):
    """A teaching slot a teacher grants access to as a unit (e.g. 'E1', 'E2')."""
    __tablename__ = 'class_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    members = db.relationship('User', secondary=class_group_members,
                              backref=db.backref('class_groups', lazy=True), lazy=True)
    access_grants = db.relationship('AccessGrant', backref='class_group', lazy=True)
    
    __table_args__ = (db.UniqueConstraint('teacher_id', 'name', name='unique_teacher_group_name'),)

class Set(db.Model):
    __tablename__ = 'sets'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # How the work is handed in:
    # 'quiz'       -> answers typed into the portal, one box per question
    # 'assignment' -> one Word/PDF written answer sheet uploaded per attempt
    delivery_mode = db.Column(db.String(20), default='quiz')

    # How students may use the uploaded materials during an attempt:
    # 'open_book'  -> visible while they answer
    # 'closed_book' -> visible only before the attempt is started
    book_mode = db.Column(db.String(20), default='open_book')
    # Minutes allowed per attempt; NULL means no time limit
    time_limit_minutes = db.Column(db.Integer)

    # Two separate ends to the submission window:
    # due_at      -> soft. Work still arrives, but is recorded as late.
    # submissions_close_at -> hard. The link stops accepting anything at all.
    due_at = db.Column(db.DateTime)
    submissions_close_at = db.Column(db.DateTime)

    # Pool-based sets hand each student a random subset of a generated question
    # pool instead of the same fixed list, so neighbours rarely see the same
    # questions. `questions_per_student` is how many they each answer.
    is_pool_based = db.Column(db.Boolean, default=False)
    questions_per_student = db.Column(db.Integer)
    pool_topic = db.Column(db.String(200))
    # Shape of question to write, e.g. 'short answer', 'numerical', 'one word'
    pool_kind = db.Column(db.String(80))
    pool_difficulty = db.Column(db.Integer)
    pool_notes = db.Column(db.Text)
    
    # Relationships
    materials = db.relationship('Material', backref='set', lazy=True, cascade='all, delete-orphan')
    questions = db.relationship('Question', backref='set', lazy=True, cascade='all, delete-orphan')
    access_grants = db.relationship('AccessGrant', backref='set', lazy=True, cascade='all, delete-orphan')
    submissions = db.relationship('Submission', backref='set', lazy=True, cascade='all, delete-orphan')

class Material(db.Model):
    __tablename__ = 'materials'
    
    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))  # pdf, docx, txt
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_text = db.Column(db.Text)  # Store extracted text for TF-IDF

    # 'material'      -> study material, may be consulted during an open-book attempt
    # 'question_paper' -> the question paper itself, handed to students as a download
    kind = db.Column(db.String(20), default='material')

    # Written by the app from the set's questions rather than uploaded, so the
    # paper handed to students always matches the questions on screen.
    is_generated = db.Column(db.Boolean, default=False)

class Submission(db.Model):
    """One uploaded answer sheet for a file-based (assignment) attempt.

    The student writes all their answers into a single Word/PDF document and
    uploads it. The document is split per question, each part is graded like a
    typed answer, and the resulting Log rows point back here through
    `submission_id` so the teacher can review the whole sheet as one unit."""
    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    attempt_no = db.Column(db.Integer, default=1)

    filename = db.Column(db.String(255), nullable=False)   # name the student uploaded
    filepath = db.Column(db.String(500), nullable=False)   # where we stored it
    file_type = db.Column(db.String(20))                   # pdf, docx, txt
    extracted_text = db.Column(db.Text)                    # full text we read back

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_late = db.Column(db.Boolean, default=False)  # arrived after the due date
    # Set once a teacher has looked over the split and the AI scores
    reviewed = db.Column(db.Boolean, default=False)
    teacher_note = db.Column(db.Text)
    # Short AI summary of how the sheet was split, surfaced in the review panel
    split_note = db.Column(db.Text)

    student = db.relationship('User', lazy=True)
    logs = db.relationship('Log', backref='submission', lazy=True)

class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    ideal_answer = db.Column(db.Text)  # Optional reference answer
    max_score = db.Column(db.Integer, default=10)
    # Grading harshness chosen by the teacher: 1=Very Lenient ... 5=Very Strict
    strictness = db.Column(db.Integer, default=3)
    # True when the question came out of the AI pool generator rather than being
    # typed by the teacher; pool questions are only shown as allocations.
    is_generated = db.Column(db.Boolean, default=False)
    topic = db.Column(db.String(200))
    difficulty = db.Column(db.Integer)
    
    # Relationships
    logs = db.relationship('Log', backref='question', lazy=True)

class QuestionAllocation(db.Model):
    """Which pool questions a student was handed for a given attempt, and in
    what order. Written once when the attempt starts so the questions cannot
    change underneath the student while they answer."""
    __tablename__ = 'question_allocations'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    attempt_no = db.Column(db.Integer, default=1)
    position = db.Column(db.Integer, default=0)
    allocated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    question = db.relationship('Question', lazy=True)
    
    __table_args__ = (db.UniqueConstraint('student_id', 'set_id', 'question_id', 'attempt_no',
                                          name='unique_allocation_per_attempt'),)

class AccessGrant(db.Model):
    __tablename__ = 'access_grants'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    set_id = db.Column(db.Integer, db.ForeignKey('sets.id'), nullable=False)
    # Set when the grant was issued by granting a whole class, so the teacher can
    # see where a student's access came from.
    class_group_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'))
    max_attempts = db.Column(db.Integer, default=1)
    attempts_used = db.Column(db.Integer, default=0)
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Window for the attempt currently in progress; both NULL when no attempt is open
    attempt_started_at = db.Column(db.DateTime)
    attempt_deadline = db.Column(db.DateTime)
    
    __table_args__ = (db.UniqueConstraint('student_id', 'set_id', name='unique_student_set'),)

class Log(db.Model):
    __tablename__ = 'logs'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    # Set when this answer came out of an uploaded Word/PDF answer sheet, so the
    # whole sheet can be shown together in the teacher's review panel.
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id'))
    answer = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text)
    score = db.Column(db.Float)
    max_score = db.Column(db.Integer, default=10)
    source_used = db.Column(db.String(50))  # 'material_match', 'ai_api', 'fallback_dataset'
    confidence = db.Column(db.Float)
    manually_graded = db.Column(db.Boolean, default=False)  # True when a teacher overrides the AI score
    teacher_comment = db.Column(db.Text)  # Teacher's optional note on manual correction
    submitted_late = db.Column(db.Boolean, default=False)  # Arrived after the set's time limit expired
    # Which attempt this answer belongs to, so mark sheets can pick the latest
    # attempt instead of double-counting a student's retakes.
    attempt_no = db.Column(db.Integer, default=1)
    # One-line gist of the answer, asked for separately from the full grading
    # reason so the spreadsheet stays readable.
    key_point = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
