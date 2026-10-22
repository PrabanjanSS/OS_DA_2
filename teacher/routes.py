import os
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   current_app, send_file)
from flask_login import login_required, current_user
from models import (Set, Material, Question, AccessGrant, Log, User, ClassGroup,
                    QuestionAllocation)
from extensions import db
from services.file_parser import extract_text_from_file, chunk_text
from services.validator import DEFAULT_STRICTNESS, STRICTNESS_LEVELS
from services.generator import (DEFAULT_DIFFICULTY, DIFFICULTY_LEVELS, MAX_POOL,
                                MAX_PER_STUDENT, MIN_PER_STUDENT, difficulty_profile,
                                generate_question_pool)
from services.reports import build_detailed_report, build_marksheet, workbook_bytes
from werkzeug.utils import secure_filename

teacher_bp = Blueprint('teacher', __name__)


def _owned_set_or_none(set_id):
    """Fetch a set the current teacher owns, or None if it is not theirs."""
    set_obj = Set.query.get(set_id)
    if set_obj is None or set_obj.teacher_id != current_user.id:
        return None
    return set_obj


def _owned_class_or_none(class_id):
    group = ClassGroup.query.get(class_id)
    if group is None or group.teacher_id != current_user.id:
        return None
    return group


def _grant_class(set_obj, group, max_attempts):
    """Fan a class grant out into one AccessGrant row per member.

    Attempts are counted per student, so access has to be materialised per
    student; recording `class_group_id` keeps the provenance visible.
    """
    granted = 0
    for student in group.members:
        grant = AccessGrant.query.filter_by(student_id=student.id, set_id=set_obj.id).first()
        if grant:
            grant.max_attempts = max_attempts
            grant.class_group_id = group.id
        else:
            db.session.add(AccessGrant(student_id=student.id, set_id=set_obj.id,
                                       class_group_id=group.id, max_attempts=max_attempts))
            granted += 1
    db.session.commit()
    return granted


def _parser_int(raw, default, low, high):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return min(max(value, low), high)


@teacher_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'teacher':
        flash('Access denied. Teachers only.', 'error')
        return redirect(url_for('auth.login'))
    
    sets = Set.query.filter_by(teacher_id=current_user.id).all()
    classes = ClassGroup.query.filter_by(teacher_id=current_user.id).order_by(ClassGroup.name).all()
    return render_template('teacher/dashboard.html', sets=sets, classes=classes)

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
    classes = ClassGroup.query.filter_by(teacher_id=current_user.id).order_by(ClassGroup.name).all()
    
    return render_template('teacher/view_set.html', set=set_obj, materials=materials, 
                          questions=questions, access_grants=access_grants,
                          classes=classes,
                          strictness_labels={level: data[0] for level, data in STRICTNESS_LEVELS.items()},
                          difficulty_labels={level: data[0] for level, data in DIFFICULTY_LEVELS.items()})

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
    
    max_attempts = _parser_int(request.form.get('max_attempts'), 1, 1, 10)

    # Granting a whole class is the common case; a single email still works for
    # one-off exceptions.
    class_id = (request.form.get('class_group_id') or '').strip()
    if class_id:
        group = _owned_class_or_none(int(class_id) if class_id.isdigit() else 0)
        if group is None:
            flash('Class not found.', 'error')
            return redirect(url_for('teacher.view_set', set_id=set_id))
        if not group.members:
            flash(f'{group.name} has no students yet.', 'error')
            return redirect(url_for('teacher.view_set', set_id=set_id))
        _grant_class(set_obj, group, max_attempts)
        flash(f'Access granted to all {len(group.members)} students in {group.name} '
              f'({max_attempts} attempt(s) each).', 'success')
        return redirect(url_for('teacher.view_set', set_id=set_id))

    student_email = request.form.get('student_email')
    if not student_email:
        flash('Choose a class or enter a student email.', 'error')
        return redirect(url_for('teacher.view_set', set_id=set_id))

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


# --- Classes ---------------------------------------------------------------

@teacher_bp.route('/classes')
@login_required
def classes():
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    groups = ClassGroup.query.filter_by(teacher_id=current_user.id).order_by(ClassGroup.name).all()
    return render_template('teacher/classes.html', classes=groups)


@teacher_bp.route('/classes/create', methods=['POST'])
@login_required
def create_class():
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Class name is required.', 'error')
        return redirect(url_for('teacher.classes'))

    if ClassGroup.query.filter_by(teacher_id=current_user.id, name=name).first():
        flash(f'A class called "{name}" already exists.', 'error')
        return redirect(url_for('teacher.classes'))

    group = ClassGroup(teacher_id=current_user.id, name=name,
                       description=(request.form.get('description') or '').strip() or None)
    db.session.add(group)
    db.session.commit()
    flash(f'Class "{name}" created. Add students to it below.', 'success')
    return redirect(url_for('teacher.classes'))


@teacher_bp.route('/classes/<int:class_id>/member/add', methods=['POST'])
@login_required
def add_class_member(class_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    group = _owned_class_or_none(class_id)
    if group is None:
        flash('Class not found.', 'error')
        return redirect(url_for('teacher.classes'))

    email = (request.form.get('student_email') or '').strip()
    student = User.query.filter_by(email=email, role='student').first()
    if not student:
        flash('Student not found. They need an account before joining a class.', 'error')
        return redirect(url_for('teacher.classes'))

    if student in group.members:
        flash(f'{student.name} is already in {group.name}.', 'info')
    else:
        group.members.append(student)
        db.session.commit()
        flash(f'{student.name} added to {group.name}.', 'success')
    return redirect(url_for('teacher.classes'))


@teacher_bp.route('/classes/<int:class_id>/member/remove', methods=['POST'])
@login_required
def remove_class_member(class_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    group = _owned_class_or_none(class_id)
    if group is None:
        flash('Class not found.', 'error')
        return redirect(url_for('teacher.classes'))

    student_id = request.form.get('student_id')
    student = User.query.get(student_id) if student_id and student_id.isdigit() else None
    if student is None or student not in group.members:
        flash('Student is not in this class.', 'error')
        return redirect(url_for('teacher.classes'))

    group.members.remove(student)
    db.session.commit()
    flash(f'{student.name} removed from {group.name}. '
          'Access already granted for a set is not withdrawn.', 'info')
    return redirect(url_for('teacher.classes'))


# --- AI question pool ------------------------------------------------------

@teacher_bp.route('/set/<int:set_id>/generate-questions', methods=['POST'])
@login_required
def generate_questions(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    set_obj = _owned_set_or_none(set_id)
    if set_obj is None:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))

    topic = (request.form.get('topic') or '').strip()
    notes = (request.form.get('pool_notes') or '').strip()
    per_student = _parser_int(request.form.get('questions_per_student'), 3,
                              MIN_PER_STUDENT, MAX_PER_STUDENT)
    difficulty = _parser_int(request.form.get('difficulty'), DEFAULT_DIFFICULTY, 1, 5)
    pool_size = _parser_int(request.form.get('pool_size'), per_student * 3, per_student, MAX_POOL)

    # Give the model the uploaded material as context when there is any.
    material_text = ' '.join(m.processed_text for m in set_obj.materials if m.processed_text)
    context = material_text[:6000]

    result = generate_question_pool(topic, per_student, difficulty, pool_size, notes, context)
    if result['error']:
        flash(result['error'], 'error')
        return redirect(url_for('teacher.view_set', set_id=set_id))

    # Replacing the pool clears the old one; previous allocations are left in
    # place so already-submitted answers keep pointing at real questions.
    Question.query.filter_by(set_id=set_id, is_generated=True).delete()

    for item in result['questions']:
        db.session.add(Question(
            set_id=set_id,
            question_text=item['question'],
            ideal_answer=item['ideal_answer'],
            max_score=10,
            strictness=DEFAULT_STRICTNESS,
            is_generated=True,
            topic=topic,
            difficulty=difficulty,
        ))

    set_obj.is_pool_based = True
    set_obj.questions_per_student = per_student
    set_obj.pool_topic = topic
    set_obj.pool_difficulty = difficulty
    set_obj.pool_notes = notes or None
    db.session.commit()

    label, _ = difficulty_profile(difficulty)
    flash(f'Generated {len(result["questions"])} questions on "{topic}" ({label} difficulty). '
          f'Each student will be given {per_student} of them at random.', 'success')
    return redirect(url_for('teacher.view_set', set_id=set_id))


@teacher_bp.route('/set/<int:set_id>/pool/disable', methods=['POST'])
@login_required
def disable_pool(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    set_obj = _owned_set_or_none(set_id)
    if set_obj is None:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))

    set_obj.is_pool_based = False
    db.session.commit()
    flash('Random allocation switched off. Students now see the fixed question list.', 'info')
    return redirect(url_for('teacher.view_set', set_id=set_id))


@teacher_bp.route('/set/<int:set_id>/pool/clear', methods=['POST'])
@login_required
def clear_pool(set_id):
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    set_obj = _owned_set_or_none(set_id)
    if set_obj is None:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))

    # Allocations reference the questions, so they have to go first.
    QuestionAllocation.query.filter_by(set_id=set_id).delete()
    removed = Question.query.filter_by(set_id=set_id, is_generated=True).delete()
    set_obj.is_pool_based = False
    set_obj.questions_per_student = None
    db.session.commit()
    flash(f'Removed {removed} generated questions and their allocations.', 'success')
    return redirect(url_for('teacher.view_set', set_id=set_id))


# --- Spreadsheet exports ---------------------------------------------------

@teacher_bp.route('/set/<int:set_id>/export/detailed')
@login_required
def export_detailed(set_id):
    """One assignment, one class: every answer with the AI's reasoning."""
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    set_obj = _owned_set_or_none(set_id)
    if set_obj is None:
        flash('Access denied.', 'error')
        return redirect(url_for('teacher.dashboard'))

    class_id = request.args.get('class_group_id', '')
    group = None
    if class_id == 'all':
        group = None
    elif class_id.isdigit():
        group = _owned_class_or_none(int(class_id))
        if group is None:
            flash('Class not found.', 'error')
            return redirect(url_for('teacher.view_set', set_id=set_id))
    else:
        flash('Choose a class to export.', 'error')
        return redirect(url_for('teacher.view_set', set_id=set_id))

    workbook = build_detailed_report(set_obj, group)
    suffix = group.name if group else 'all-classes'
    filename = f'{secure_filename(set_obj.title) or "set"}-{suffix}-detailed.xlsx'
    return send_file(workbook_bytes(workbook), as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@teacher_bp.route('/export/marksheet')
@login_required
def export_marksheet():
    """One class, every assignment: a register of totals."""
    if current_user.role != 'teacher':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    class_id = request.args.get('class_group_id', '')
    group = _owned_class_or_none(int(class_id)) if class_id.isdigit() else None
    if group is None:
        flash('Choose a class to export.', 'error')
        return redirect(url_for('teacher.dashboard'))

    set_ids = request.args.getlist('set_ids')
    query = Set.query.filter_by(teacher_id=current_user.id)
    if set_ids:
        wanted = [int(sid) for sid in set_ids if sid.isdigit()]
        query = query.filter(Set.id.in_(wanted)) if wanted else query.filter(False)
    sets = query.order_by(Set.created_at).all()

    if not sets:
        flash('No assignments to include. Create a set first.', 'error')
        return redirect(url_for('teacher.dashboard'))

    workbook = build_marksheet(group, sets)
    filename = f'{secure_filename(group.name) or "class"}-marksheet.xlsx'
    return send_file(workbook_bytes(workbook), as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
