import os
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, send_from_directory, send_file)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import Set, Question, Material, AccessGrant, Log, Submission
from extensions import db
from services.allocation import allocate_questions, allocated_questions
from services.generator import kind_profile
from services.reports import question_paper_bytes
from services.file_parser import extract_text_from_file
from services.splitter import split_answer_sheet
from services.validator import AnswerValidator
from services.concurrency import attempt_counter, log_submission

student_bp = Blueprint('student', __name__)


def _window_state(set_obj, now=None):
    """Where we are in the set's submission window: (is_open, is_overdue).

    `submissions_close_at` is the hard close: past it the link accepts nothing
    at all. `due_at` is the soft one: work still arrives, but it is recorded as
    late. Either can be left unset.
    """
    now = now or datetime.utcnow()
    is_open = set_obj.submissions_close_at is None or now <= set_obj.submissions_close_at
    is_overdue = set_obj.due_at is not None and now > set_obj.due_at
    return is_open, is_overdue


def _requires_start(set_obj):
    """A timed, closed-book or pool-based set needs an explicit start.

    Pool-based sets need one because the questions are handed out at that
    moment; showing the answer form first would mean showing an empty paper.
    """
    closed_book = (set_obj.book_mode or 'open_book') == 'closed_book'
    return closed_book or set_obj.time_limit_minutes is not None or bool(set_obj.is_pool_based)


def _questions_for_attempt(set_obj, attempt_no, started, allow_allocate=True):
    """The questions this student should be looking at right now.

    `attempt_no` is required rather than derived from the grant because the
    counter moves at different points: it still counts *completed* attempts while
    a page is being rendered, but a submission has already incremented it before
    it reaches here. Deriving it inside drifted by one on the submit path, so the
    sheet was graded against a freshly drawn paper instead of the one the student
    had downloaded.

    `allow_allocate` is off for grading: there the stored allocation is the
    single source of truth, and drawing a replacement would mean marking answers
    against questions the student never saw.
    """
    if not set_obj.is_pool_based:
        return Question.query.filter_by(set_id=set_obj.id).all()

    if not started:
        return []

    questions = allocated_questions(current_user.id, set_obj.id, attempt_no)
    if not questions and allow_allocate:
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
            window_open, is_overdue = _window_state(set_obj)
            accessible_sets.append({
                'set': set_obj,
                'max_attempts': grant.max_attempts,
                'attempts_used': grant.attempts_used,
                'remaining': grant.max_attempts - grant.attempts_used,
                'window_open': window_open,
                'is_overdue': is_overdue,
                'is_assignment': (set_obj.delivery_mode or 'quiz') == 'assignment',
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
    # attempts_used counts completed attempts, so any attempt in progress is the
    # next number up.
    questions = _questions_for_attempt(set_obj, grant.attempts_used + 1, started)
    awaiting_start = _requires_start(set_obj) and not started
    # Closed book: the materials are readable up to the moment the attempt
    # starts, then they are withdrawn from the page entirely.
    show_materials = awaiting_start or not closed_book

    window_open, is_overdue = _window_state(set_obj)
    is_assignment = (set_obj.delivery_mode or 'quiz') == 'assignment'
    # The question paper is the teacher's own upload of the questions; it is
    # listed separately from study material so it can be offered as the thing
    # the student writes their answers against. For a pool-based set the
    # generated paper holds the whole pool, so it is withheld: the student
    # downloads their own allocated subset instead.
    question_papers = [m for m in set_obj.materials
                       if (m.kind or 'material') == 'question_paper'
                       and not (m.is_generated and set_obj.is_pool_based)]
    study_materials = [m for m in set_obj.materials if (m.kind or 'material') != 'question_paper']

    return render_template('student/view_set.html', set=set_obj, questions=questions,
                          remaining_attempts=grant.max_attempts - grant.attempts_used,
                          materials=study_materials if show_materials else [],
                          question_papers=question_papers,
                          awaiting_start=awaiting_start,
                          closed_book=closed_book,
                          show_materials=show_materials,
                          pool_based=bool(set_obj.is_pool_based),
                          time_limit_minutes=set_obj.time_limit_minutes,
                          attempt_deadline=grant.attempt_deadline,
                          is_assignment=is_assignment,
                          window_open=window_open,
                          is_overdue=is_overdue,
                          due_at=set_obj.due_at,
                          submissions_close_at=set_obj.submissions_close_at)


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

    if not _window_state(set_obj)[0]:
        flash('The submission link for this set is closed.', 'error')
        return redirect(url_for('student.dashboard'))

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
    allocated = _questions_for_attempt(set_obj, grant.attempts_used + 1, started=True)

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

    # A pool-based set's generated paper holds every question in the pool, so it
    # is not served: the student gets their own subset from download_paper.
    if material.is_generated and set_obj.is_pool_based:
        flash('Use "Your question paper" to download the questions drawn for you.',
              'info')
        return redirect(url_for('student.view_set', set_id=set_id))

    return send_from_directory(current_app.config['UPLOAD_FOLDER'], material.filename)


@student_bp.route('/set/<int:set_id>/paper')
@login_required
def download_paper(set_id):
    """Build the student's own paper, on demand, from the questions they drew.

    A pool-based set has one generated paper on disk holding the whole pool,
    which is the teacher's copy. What the student needs is only the subset
    allocated to them, in the order they were given it - so the file is rendered
    per request rather than stored.
    """
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    grant = AccessGrant.query.filter_by(student_id=current_user.id, set_id=set_id).first()
    if not grant:
        flash('You do not have access to this set.', 'error')
        return redirect(url_for('student.dashboard'))

    set_obj = Set.query.get_or_404(set_id)
    started = grant.attempt_started_at is not None
    questions = _questions_for_attempt(set_obj, grant.attempts_used + 1, started)
    if not questions:
        flash('Your paper is drawn the moment you start the attempt.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    kind_label, _ = kind_profile(set_obj.pool_kind)
    stream = question_paper_bytes(set_obj, questions, kind_label)
    filename = f'{secure_filename(set_obj.title) or "questions"}-paper.docx'
    return send_file(
        stream,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )

@student_bp.route('/set/<int:set_id>/submit', methods=['POST'])
@login_required
def submit_answer(set_id):
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    set_obj = Set.query.get_or_404(set_id)

    # The hard close ends the set outright: unlike the due date, nothing is
    # accepted past it.
    window_open, is_overdue = _window_state(set_obj)
    if not window_open:
        flash('The submission link for this set is closed.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

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

    # An answer that arrives after the set's due date or after this attempt's
    # own time limit is still graded; it is recorded as late either way.
    submitted_late = is_overdue or bool(
        grant.attempt_deadline and datetime.utcnow() > grant.attempt_deadline)
    
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

@student_bp.route('/set/<int:set_id>/submit-sheet', methods=['POST'])
@login_required
def submit_answersheet(set_id):
    """File-based hand-in: one Word/PDF sheet, split and graded per question.

    The student writes every answer into a single document; the sheet is cut
    back apart per question here, and each part is graded exactly like a typed
    answer. The submission is left unreviewed so the teacher can check how the
    document was split before trusting the scores.
    """
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    set_obj = Set.query.get_or_404(set_id)

    if (set_obj.delivery_mode or 'quiz') != 'assignment':
        flash('This set takes typed answers, not an uploaded sheet.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    window_open, is_overdue = _window_state(set_obj)
    if not window_open:
        flash('The submission link for this set is closed.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    grant = AccessGrant.query.filter_by(student_id=current_user.id, set_id=set_id).first()
    if grant is None:
        flash('You do not have access to this set.', 'error')
        return redirect(url_for('student.dashboard'))

    if _requires_start(set_obj) and grant.attempt_started_at is None:
        flash('Start the attempt before submitting your sheet.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    file = request.files.get('answer_file')
    if file is None or not file.filename:
        flash('Choose a PDF or Word document to upload.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    safe_name = secure_filename(file.filename)
    file_ext = safe_name.rsplit('.', 1)[1].lower() if '.' in safe_name else ''
    if file_ext not in current_app.config['ALLOWED_EXTENSIONS']:
        flash(f'{file_ext.upper() or "That"} files are not accepted. Upload a PDF, DOCX or TXT.', 'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    # The attempt being handed in is the one that was started, which is one up
    # from the completed count - read it before the counter moves, and read only:
    # grading has to use the paper the student was actually given, so a missing
    # allocation is reported rather than papered over with a fresh draw.
    attempt_no = grant.attempts_used + 1
    questions = _questions_for_attempt(set_obj, attempt_no, started=True, allow_allocate=False)
    if not questions:
        flash('No questions are allocated to this attempt, so there is nothing to '
              'grade against. Start the attempt again before submitting.',
              'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    # Count the attempt atomically before spending it on the file
    def check_and_increment(student_id, target_set_id):
        row = AccessGrant.query.filter_by(student_id=student_id, set_id=target_set_id).first()
        if not row or row.attempts_used >= row.max_attempts:
            return False, None
        row.attempts_used += 1
        db.session.commit()
        return True, row

    can_submit, grant = attempt_counter(current_user.id, set_id, check_and_increment)
    if not can_submit:
        flash('No attempts remaining or access denied.', 'error')
        return redirect(url_for('student.dashboard'))

    # Namespaced on disk: two students handing in "answers.docx" must not
    # overwrite each other, and a retake must not clobber the previous sheet.
    stored_name = (f'set{set_id}-user{current_user.id}-'
                   f'{int(datetime.utcnow().timestamp())}-{safe_name}')
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_name)
    file.save(filepath)

    extracted_text = extract_text_from_file(filepath, file_ext)
    if not extracted_text or not extracted_text.strip():
        flash('No text could be read from that document. Upload one with selectable text, not a scan.',
              'error')
        return redirect(url_for('student.view_set', set_id=set_id))

    # Late means "after the due date" as well as "after this attempt's own clock"
    submitted_late = is_overdue or bool(
        grant.attempt_deadline and datetime.utcnow() > grant.attempt_deadline)

    submission = Submission(
        student_id=current_user.id,
        set_id=set_id,
        attempt_no=grant.attempts_used,
        filename=safe_name,
        filepath=filepath,
        file_type=file_ext,
        extracted_text=extracted_text,
        submitted_late=submitted_late,
        reviewed=False,
    )
    db.session.add(submission)
    db.session.commit()

    split = split_answer_sheet(extracted_text, questions)
    submission.split_note = split['note']
    db.session.commit()

    validator = AnswerValidator()
    materials = [m.processed_text for m in set_obj.materials if m.processed_text]
    if materials:
        validator.index_set_materials(materials)

    results = []
    unanswered = 0
    for question in questions:
        answer = (split['answers'].get(question.id) or '').strip()
        if not answer:
            # Nothing was located for this question in the document; it is left
            # ungraded rather than scored zero, and reported back to the student.
            unanswered += 1
            continue

        validation_result = validator.validate_answer(
            question.question_text, answer, question.ideal_answer, question.strictness)

        db.session.add(Log(
            student_id=current_user.id,
            question_id=question.id,
            submission_id=submission.id,
            answer=answer,
            ai_response=validation_result['explanation'],
            score=validation_result['score'],
            max_score=validation_result['max_score'],
            source_used=validation_result['source_used'],
            confidence=validation_result['confidence'],
            submitted_late=submitted_late,
            key_point=validation_result.get('key_point'),
            attempt_no=grant.attempts_used,
        ))
        db.session.commit()

        results.append({
            'question': question.question_text,
            'answer': answer,
            'score': validation_result['score'],
            'max_score': validation_result['max_score'],
            'explanation': validation_result['explanation'],
            'source': validation_result['source_used'],
        })

    total_score = sum(r['score'] for r in results)
    max_total = sum(r['max_score'] for r in results)

    # Close the attempt window so a retake starts the clock afresh
    grant.attempt_started_at = None
    grant.attempt_deadline = None
    db.session.commit()

    return render_template('student/results.html', set=set_obj, results=results,
                          total_score=total_score, max_total=max_total,
                          submitted_late=submitted_late,
                          from_sheet=True, split_note=split['note'],
                          unanswered=unanswered)


@student_bp.route('/history')
@login_required
def history():
    if current_user.role != 'student':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))
    
    logs = Log.query.filter_by(student_id=current_user.id).order_by(Log.timestamp.desc()).all()
    
    return render_template('student/history.html', logs=logs)
