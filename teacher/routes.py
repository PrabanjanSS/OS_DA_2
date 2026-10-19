import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import Set, Material, Question, AccessGrant, Log, User
from extensions import db
from services.file_parser import extract_text_from_file, chunk_text
from services.validator import DEFAULT_STRICTNESS, STRICTNESS_LEVELS
from werkzeug.utils import secure_filename

teacher_bp = Blueprint('teacher', __name__)

@teacher_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'teacher':
        flash('Access denied. Teachers only.', 'error')
        return redirect(url_for('auth.login'))
    
    sets = Set.query.filter_by(teacher_id=current_user.id).all()
    return render_template('teacher/dashboard.html', sets=sets)

@teacher_bp.route('/set/create', methods=['GET', 'POST'])
@login_required
def create_set():
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')

        # Open book keeps the materials visible while the student answers;
        # closed book shows them only before the attempt is started.
        book_mode = request.form.get('book_mode', 'open_book')
        if book_mode not in ('open_book', 'closed_book'):
            book_mode = 'open_book'

        # Blank or 0 means no time limit; otherwise clamped to a sane range
        raw_limit = (request.form.get('time_limit_minutes') or '').strip()
        try:
            time_limit_minutes = int(raw_limit) if raw_limit else None
        except ValueError:
            time_limit_minutes = None
        if time_limit_minutes is not None:
            time_limit_minutes = min(max(time_limit_minutes, 1), 600)

        new_set = Set(teacher_id=current_user.id, title=title, description=description,
                      book_mode=book_mode, time_limit_minutes=time_limit_minutes)
        db.session.add(new_set)
        db.session.commit()
        
        flash(f'Set "{title}" created successfully!', 'success')
        return redirect(url_for('teacher.view_set', set_id=new_set.id))
    
    return render_template('teacher/create_set.html')

@teacher_bp.route('/set/<int:set_id>')
@login_required
def view_set(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    set_obj = Set.query.get_or_404(set_id)
    if set_obj.teacher_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))
    
    materials = Material.query.filter_by(set_id=set_id).all()
    questions = Question.query.filter_by(set_id=set_id).all()
    access_grants = AccessGrant.query.filter_by(set_id=set_id).all()
    
    return render_template('teacher/view_set.html', set=set_obj, materials=materials, 
                          questions=questions, access_grants=access_grants,
                          strictness_labels={level: data[0] for level, data in STRICTNESS_LEVELS.items()})

@teacher_bp.route('/set/<int:set_id>/delete', methods=['POST'])
@login_required
def delete_set(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    set_obj = Set.query.get_or_404(set_id)
    if set_obj.teacher_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))

    title = set_obj.title

    # Submissions point at questions, so clear them before the questions cascade away
    submissions = db.session.query(Log).join(Question, Log.question_id == Question.id).\
        filter(Question.set_id == set_id).all()
    for log in submissions:
        db.session.delete(log)
    db.session.commit()

    # Remove the uploaded files from disk
    for material in set_obj.materials:
        try:
            if material.filepath and os.path.exists(material.filepath):
                os.remove(material.filepath)
        except OSError:
            pass  # a missing file shouldn't stop the set from being deleted

    # Cascade removes the set's questions, materials and access grants
    db.session.delete(set_obj)
    db.session.commit()

    flash(f'Set "{title}" and all its questions were deleted.', 'success')
    return redirect(url_for('teacher.dashboard'))

@teacher_bp.route('/set/<int:set_id>/upload', methods=['POST'])
@login_required
def upload_material(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    set_obj = Set.query.get_or_404(set_id)
    if set_obj.teacher_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))
    
    if 'file' not in request.files:
        flash('No file uploaded.', 'error')
        return redirect(url_for('teacher.view_set', set_id=set_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('teacher.view_set', set_id=set_id))
    
    if file:
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if file_ext not in current_app.config['ALLOWED_EXTENSIONS']:
            flash(f'File type {file_ext} not allowed. Use PDF, DOCX, or TXT.', 'error')
            return redirect(url_for('teacher.view_set', set_id=set_id))
        
        # Save file
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract text
        extracted_text = extract_text_from_file(filepath, file_ext)
        
        # Store in database
        material = Material(
            set_id=set_id,
            filename=filename,
            filepath=filepath,
            file_type=file_ext,
            processed_text=extracted_text
        )
        db.session.add(material)
        db.session.commit()
        
        flash(f'Material "{filename}" uploaded and processed successfully!', 'success')
        return redirect(url_for('teacher.view_set', set_id=set_id))

@teacher_bp.route('/set/<int:set_id>/question/add', methods=['POST'])
@login_required
def add_question(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    set_obj = Set.query.get_or_404(set_id)
    if set_obj.teacher_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))
    
    question_text = request.form.get('question_text')
    ideal_answer = request.form.get('ideal_answer')
    max_score = int(request.form.get('max_score', 10))

    # How harshly the AI should grade this question (1 = very lenient, 5 = very strict)
    try:
        strictness = int(request.form.get('strictness', DEFAULT_STRICTNESS))
    except (TypeError, ValueError):
        strictness = DEFAULT_STRICTNESS
    strictness = min(max(strictness, 1), 5)

    question = Question(
        set_id=set_id,
        question_text=question_text,
        ideal_answer=ideal_answer,
        max_score=max_score,
        strictness=strictness
    )
    db.session.add(question)
    db.session.commit()
    
    flash('Question added successfully!', 'success')
    return redirect(url_for('teacher.view_set', set_id=set_id))

@teacher_bp.route('/set/<int:set_id>/grant', methods=['POST'])
@login_required
def grant_access(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    set_obj = Set.query.get_or_404(set_id)
    if set_obj.teacher_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))
    
    student_email = request.form.get('student_email')
    max_attempts = int(request.form.get('max_attempts', 1))
    
    student = User.query.filter_by(email=student_email, role='student').first()
    if not student:
        flash('Student not found. Please check the email.', 'error')
        return redirect(url_for('teacher.view_set', set_id=set_id))
    
    # Check if already granted
    existing = AccessGrant.query.filter_by(student_id=student.id, set_id=set_id).first()
    if existing:
        existing.max_attempts = max_attempts
        db.session.commit()
        flash(f'Access updated for {student.name}.', 'success')
    else:
        grant = AccessGrant(student_id=student.id, set_id=set_id, max_attempts=max_attempts)
        db.session.add(grant)
        db.session.commit()
        flash(f'Access granted to {student.name} for {max_attempts} attempts.', 'success')
    
    return redirect(url_for('teacher.view_set', set_id=set_id))

@teacher_bp.route('/set/<int:set_id>/analytics')
@login_required
def set_analytics(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    set_obj = Set.query.get_or_404(set_id)
    if set_obj.teacher_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))
    
    # Get all logs for this set
    logs = db.session.query(Log, User).join(User, Log.student_id == User.id).\
        join(Question, Log.question_id == Question.id).\
        filter(Question.set_id == set_id).all()
    
    # Calculate analytics
    total_submissions = len(logs)
    avg_score = sum(log[0].score for log in logs) / total_submissions if total_submissions > 0 else 0
    
    # Source usage breakdown
    source_counts = {}
    for log, _ in logs:
        source = log.source_used or 'unknown'
        source_counts[source] = source_counts.get(source, 0) + 1
    
    return render_template('teacher/analytics.html', set=set_obj, logs=logs, 
                          total_submissions=total_submissions, avg_score=avg_score,
                          source_counts=source_counts)


@teacher_bp.route('/log/<int:log_id>/correct', methods=['POST'])
@login_required
def manual_correct(log_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    log = Log.query.get_or_404(log_id)
    question = Question.query.get(log.question_id)
    set_obj = Set.query.get(question.set_id)
    if set_obj.teacher_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))

    try:
        score = float(request.form.get('score'))
    except (TypeError, ValueError):
        flash('Please enter a valid numeric score.', 'error')
        return redirect(url_for('teacher.set_analytics', set_id=set_obj.id))

    # Keep the corrected score within the valid range
    max_score = log.max_score or 10
    score = max(0.0, min(score, max_score))

    log.score = score
    log.manually_graded = True
    comment = (request.form.get('teacher_comment') or '').strip()
    if comment:
        log.teacher_comment = comment
    db.session.commit()

    flash(f'Score corrected to {score:g}/{max_score} for {log.student.name}.', 'success')
    return redirect(url_for('teacher.set_analytics', set_id=set_obj.id))
