from datetime import datetime, timedelta

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, send_from_directory)
from flask_login import login_required, current_user
from models import Set, Question, Material, AccessGrant, Log
from extensions import db
from services.allocation import allocate_questions, allocated_questions
from services.validator import AnswerValidator
from services.concurrency import attempt_counter, log_submission

student_bp = Blueprint('student', __name__)


def _requires_start(set_obj):
    """A timed, closed-book or pool-based set needs an explicit start.

    Pool-based sets need one because the questions are handed out at that
    moment; showing the answer form first would mean showing an empty paper.
    """
    closed_book = (set_obj.book_mode or 'open_book') == 'closed_book'
    return closed_book or set_obj.time_limit_minutes is not None or bool(set_obj.is_pool_based)


def _questions_for_attempt(set_obj, grant, started):
    """The questions this student should be looking at right now."""
    if not set_obj.is_pool_based:
        return Question.query.filter_by(set_id=set_obj.id).all()

    if not started:
        return []
    attempt_no = grant.attempts_used + 1
    questions = allocated_questions(current_user.id, set_obj.id, attempt_no)
    if not questions:
        # An attempt started before the pool existed, or an allocation was
        # cleared: hand one out now rather than showing an empty paper.
        questions = allocate_questions(set_obj, current_user.id, attempt_no)
    return questions

@student_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'student':
        flash('Access denied. Students only.', 'error')
        return redirect(url_for('auth.login'))
    
    # Get all sets the student has access to
    access_grants = AccessGrant.query.filter_by(student_id=current_user.id).all()
    accessible_sets = []
    
    for grant in access_grants:
        set_obj = Set.query.get(grant.set_id)
        if set_obj:
            accessible_sets.append({
                'set': set_obj,
                'max_attempts': grant.max_attempts,
                'attempts_used': grant.attempts_used,
                'remaining': grant.max_attempts - grant.attempts_used
            })
    
    return render_template('student/dashboard.html', accessible_sets=accessible_sets)

@student_bp.route('/set/<int:set_id>')
@login_required
def view_set(set_id):
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    # Check if student has access
    grant = AccessGrant.query.filter_by(student_id=current_user.id, set_id=set_id).first()
    if not grant:
        flash('You do not have access to this set.', 'error')
        return redirect(url_for('student.dashboard'))
    
    # Check if attempts remaining
    if grant.attempts_used >= grant.max_attempts:
        flash('You have used all your attempts for this set.', 'error')
        return redirect(url_for('student.dashboard'))
    
    set_obj = Set.query.get_or_404(set_id)

    closed_book = (set_obj.book_mode or 'open_book') == 'closed_book'
    started = grant.attempt_started_at is not None
    questions = _questions_for_attempt(set_obj, grant, started)
    awaiting_start = _requires_start(set_obj) and not started
    # Closed book: the materials are readable up to the moment the attempt
    # starts, then they are withdrawn from the page entirely.
    show_materials = awaiting_start or not closed_book

    return render_template('student/view_set.html', set=set_obj, questions=questions,
                          remaining_attempts=grant.max_attempts - grant.attempts_used,
                          materials=set_obj.materials if show_materials else [],
                          awaiting_start=awaiting_start,
                          closed_book=closed_book,
                          show_materials=show_materials,
                          pool_based=bool(set_obj.is_pool_based),
                          time_limit_minutes=set_obj.time_limit_minutes,
                          attempt_deadline=grant.attempt_deadline)


@student_bp.route('/set/<int:set_id>/start', methods=['POST'])
@login_required
def start_attempt(set_id):
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    grant = AccessGrant.query.filter_by(student_id=current_user.id, set_id=set_id).first()
    if not grant:
        flash('You do not have access to this set.', 'error')
        return redirect(url_for('student.dashboard'))

    if grant.attempts_used >= grant.max_attempts:
        flash('You have used all your attempts for this set.', 'error')
        return redirect(url_for('student.dashboard'))

    set_obj = Set.query.get_or_404(set_id)

    # Starting the attempt is what begins the clock, what withdraws the
    # materials from a closed-book student's view, and - for a pool-based set -
    # what hands out this student's questions.
    now = datetime.utcnow()
    grant.attempt_started_at = now
    grant.attempt_deadline = (now + timedelta(minutes=set_obj.time_limit_minutes)
                              if set_obj.time_limit_minutes else None)
    db.session.commit()

    # attempts_used still counts completed attempts, so the one starting now is
    # the next number up.
    allocated = _questions_for_attempt(set_obj, grant, started=True)

    if set_obj.is_pool_based:
        flash(f'Attempt started. You have been given {len(allocated)} questions '
              f'drawn at random from the pool.', 'success')
    elif set_obj.time_limit_minutes:
        flash(f'Attempt started. You have {set_obj.time_limit_minutes} minutes.', 'success')
    else:
        flash('Attempt started.', 'success')
    return redirect(url_for('student.view_set', set_id=set_id))


@student_bp.route('/set/<int:set_id>/material/<int:material_id>')
@login_required
def view_material(set_id, material_id):
    """Serve an uploaded material to a student who has been granted this set."""
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    grant = AccessGrant.query.filter_by(student_id=current_user.id, set_id=set_id).first()
    if not grant:
        flash('You do not have access to this set.', 'error')
        return redirect(url_for('student.dashboard'))

    set_obj = Set.query.get_or_404(set_id)

    # Closed book: materials stay closed for as long as an attempt window is open
    if (set_obj.book_mode or 'open_book') == 'closed_book' and grant.attempt_started_at is not None:
        flash('Materials are not available during a closed-book attempt.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    material = Material.query.get_or_404(material_id)
    if material.set_id != set_id:
        flash('Material not found.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    return send_from_directory(current_app.config['UPLOAD_FOLDER'], material.filename)

@student_bp.route('/set/<int:set_id>/submit', methods=['POST'])
@login_required
def submit_answer(set_id):
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    set_obj = Set.query.get_or_404(set_id)

    # A timed or closed-book set must be started first, otherwise the clock
    # never runs and the materials never close.
    open_grant = AccessGrant.query.filter_by(student_id=current_user.id, set_id=set_id).first()
    if _requires_start(set_obj) and (open_grant is None or open_grant.attempt_started_at is None):
        flash('Start the attempt before submitting your answers.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    # Check access and attempts (thread-safe)
    def check_and_increment(student_id, set_id):
        grant = AccessGrant.query.filter_by(student_id=student_id, set_id=set_id).first()
        if not grant or grant.attempts_used >= grant.max_attempts:
            return False, None
        grant.attempts_used += 1
        db.session.commit()
        return True, grant
    
    can_submit, grant = attempt_counter(current_user.id, set_id, check_and_increment)
    
    if not can_submit:
        flash('No attempts remaining or access denied.', 'error')
        return redirect(url_for('student.dashboard'))
    
    # A pool-based paper is the allocation handed out at start, not the whole
    # pool. Grading every pool question would also read answers for questions
    # this student was never shown.
    if set_obj.is_pool_based:
        questions = allocated_questions(current_user.id, set_id, grant.attempts_used)
        if not questions:
            questions = allocate_questions(set_obj, current_user.id, grant.attempts_used)
    else:
        questions = Question.query.filter_by(set_id=set_id).all()

    # An answer that arrives after the deadline is still graded; it is recorded
    # as late so the teacher can see the limit was overrun.
    submitted_late = bool(grant.attempt_deadline and datetime.utcnow() > grant.attempt_deadline)
    
    # Initialize validator with set materials
    validator = AnswerValidator()
    materials = [m.processed_text for m in set_obj.materials if m.processed_text]
    if materials:
        validator.index_set_materials(materials)
    
    # Process each question answer
    results = []
    for question in questions:
        answer = request.form.get(f'answer_{question.id}')
        if not answer:
            continue
        
        # Validate answer (could be run in thread pool for async)
        validation_result = validator.validate_answer(
            question.question_text,
            answer,
            question.ideal_answer,
            question.strictness
        )
        
        # Log the submission (thread-safe)
        def create_log():
            log = Log(
                student_id=current_user.id,
                question_id=question.id,
                answer=answer,
                ai_response=validation_result['explanation'],
                score=validation_result['score'],
                max_score=validation_result['max_score'],
                source_used=validation_result['source_used'],
                confidence=validation_result['confidence'],
                submitted_late=submitted_late,
                key_point=validation_result.get('key_point'),
                attempt_no=grant.attempts_used
            )
            db.session.add(log)
            db.session.commit()
            return log
        
        log_submission(create_log)
        
        results.append({
            'question': question.question_text,
            'answer': answer,
            'score': validation_result['score'],
            'max_score': validation_result['max_score'],
            'explanation': validation_result['explanation'],
            'source': validation_result['source_used']
        })
    
    total_score = sum(r['score'] for r in results)
    max_total = sum(r['max_score'] for r in results)

    # Close the attempt window so a later attempt starts the clock afresh
    grant.attempt_started_at = None
    grant.attempt_deadline = None
    db.session.commit()

    return render_template('student/results.html', set=set_obj, results=results,
                          total_score=total_score, max_total=max_total,
                          submitted_late=submitted_late)

@student_bp.route('/history')
@login_required
def history():
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    logs = Log.query.filter_by(student_id=current_user.id).order_by(Log.timestamp.desc()).all()
    
    return render_template('student/history.html', logs=logs)
