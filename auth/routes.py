import hmac

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from models import User
from extensions import db

auth_bp = Blueprint('auth', __name__)


def _dashboard_redirect():
    """Send an already-authenticated user to their role's dashboard."""
    if current_user.role == 'teacher':
        return redirect(url_for('teacher.dashboard'))
    return redirect(url_for('student.dashboard'))


def _teacher_code_configured():
    return bool(current_app.config.get('TEACHER_SIGNUP_CODE'))


def _teacher_code_matches(candidate):
    expected = current_app.config.get('TEACHER_SIGNUP_CODE') or ''
    return hmac.compare_digest(candidate or '', expected)


def _register(name, email, password, role):
    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Open self-registration for students only.

    Teacher accounts are created through the code-gated /signup/teacher flow,
    so the role is never taken from the submitted form.
    """
    if current_user.is_authenticated:
        return _dashboard_redirect()

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login.', 'error')
            return redirect(url_for('auth.signup'))

        _register(name, email, password, 'student')

        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/signup.html')


@auth_bp.route('/signup/teacher', methods=['GET', 'POST'])
def teacher_signup():
    """Protected gateway for teacher registration, in two steps.

    Step 1 unlocks the form with the shared access code; step 2 creates the
    account. Without the code the form is never rendered.
    """
    if current_user.is_authenticated:
        return _dashboard_redirect()

    if request.method == 'POST' and request.form.get('action') == 'unlock':
        if not _teacher_code_configured():
            flash('Teacher sign-up is disabled. Contact the administrator.', 'error')
        elif _teacher_code_matches(request.form.get('access_code')):
            session['teacher_signup_unlocked'] = True
        else:
            flash('Invalid teacher access code.', 'error')
        return redirect(url_for('auth.teacher_signup'))

    unlocked = session.get('teacher_signup_unlocked', False)

    if request.method == 'POST':
        if not unlocked:
            flash('Enter the teacher access code first.', 'error')
            return redirect(url_for('auth.teacher_signup'))

        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login.', 'error')
            return redirect(url_for('auth.teacher_signup'))

        _register(name, email, password, 'teacher')
        session.pop('teacher_signup_unlocked', None)

        flash('Teacher account created successfully! Please login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template(
        'auth/teacher_signup.html',
        unlocked=unlocked,
        configured=_teacher_code_configured(),
    )


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _dashboard_redirect()

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome back, {user.name}!', 'success')

            # Redirect based on role
            if user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
            else:
                return redirect(url_for('student.dashboard'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
