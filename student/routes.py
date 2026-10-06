from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import Set, Question, AccessGrant, Log
from extensions import db
from services.validator import AnswerValidator
from services.concurrency import attempt_counter, log_submission

student_bp = Blueprint('student', __name__)

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
    questions = Question.query.filter_by(set_id=set_id).all()
    
    return render_template('student/view_set.html', set=set_obj, questions=questions, 
                          remaining_attempts=grant.max_attempts - grant.attempts_used)

@student_bp.route('/set/<int:set_id>/submit', methods=['POST'])
@login_required
def submit_answer(set_id):
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
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
    
    set_obj = Set.query.get_or_404(set_id)
    questions = Question.query.filter_by(set_id=set_id).all()
    
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
            question.ideal_answer
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
                confidence=validation_result['confidence']
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
    
    return render_template('student/results.html', set=set_obj, results=results,
                          total_score=total_score, max_total=max_total)

@student_bp.route('/history')
@login_required
def history():
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    logs = Log.query.filter_by(student_id=current_user.id).order_by(Log.timestamp.desc()).all()
    
    return render_template('student/history.html', logs=logs)
