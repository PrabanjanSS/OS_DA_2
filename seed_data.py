"""Seed the database with a usable teaching scenario.

Creates a teacher account, two teaching slots ('E1' and 'E2') with student
profiles in each, and three assignments (DA1-DA3) granted to both slots, so the
class-based granting and the two spreadsheet exports have something real to work
with.

Run it from the project root:

    python3 seed_data.py                 # accounts, classes, sets, sample marks
    python3 seed_data.py --no-samples    # skip the sample submissions

Re-running is safe: anything that already exists is left alone.

The sample submissions are graded by the app's own local grading path with the
AI disabled, so they are fast, offline and deterministic. They exist purely so
the exports are demonstrable - delete them from the analytics page if you want a
clean sheet.
"""
import argparse
from datetime import datetime, timedelta

from app import create_app
from extensions import db
from models import (AccessGrant, ClassGroup, Log, Question, Set, User)
from teacher.routes import sync_question_paper
from services.validator import AnswerValidator

TEACHER_EMAIL = 'teacher_test@example.com'
TEACHER_NAME = 'Test Teacher'
# Every seeded account shares this password so the demo is easy to log into.
DEFAULT_PASSWORD = 'password123'

CLASSES = {
    'E1': 'OS slot E1 - Tuesday morning batch',
    'E2': 'OS slot E2 - Thursday morning batch',
}

STUDENTS = {
    'E1': [
        ('Aarav Menon', 'aarav.menon@example.com'),
        ('Diya Krishnan', 'diya.krishnan@example.com'),
        ('Rohan Iyer', 'rohan.iyer@example.com'),
        ('Sneha Pillai', 'sneha.pillai@example.com'),
        ('Kabir Nair', 'kabir.nair@example.com'),
        ('Ananya Rao', 'ananya.rao@example.com'),
        ('Vihaan Sharma', 'vihaan.sharma@example.com'),
        ('Meera Varma', 'meera.varma@example.com'),
    ],
    'E2': [
        ('Ishan Gupta', 'ishan.gupta@example.com'),
        ('Tara Menon', 'tara.menon@example.com'),
        ('Arjun Reddy', 'arjun.reddy@example.com'),
        ('Nikita Bose', 'nikita.bose@example.com'),
        ('Dev Patel', 'dev.patel@example.com'),
        ('Riya Choudhary', 'riya.choudhary@example.com'),
        ('Aditya Kamath', 'aditya.kamath@example.com'),
        ('Zara Khan', 'zara.khan@example.com'),
    ],
}

# Three assignments. Each question carries a model answer and a plausible student
# response used to generate the sample marks. `delivery_mode` picks how the work
# comes in ('quiz' = typed into the portal, 'assignment' = one uploaded sheet),
# `due_in_days` is the soft deadline and `closes_in_days` the hard close.
ASSIGNMENTS = [
    {
        'title': 'DA1 - Processes and Threads',
        'description': 'Assignment 1: process vs thread, context switching.',
        'delivery_mode': 'quiz',
        'due_in_days': 3,
        'closes_in_days': 10,
        'questions': [
            ('Define a process and explain how it differs from a thread.',
             'A process is a program in execution with its own address space. A thread is a unit of execution '
             'within a process and shares the address space and resources with sibling threads.',
             'A process is a program that is running and has its own memory space. A thread is a smaller unit '
             'inside the process and shares memory with other threads in the same process.'),
            ('What is a context switch and what makes it expensive?',
             'A context switch saves the state of the running process and restores another. It is expensive '
             'because of saving and reloading registers, flushing the TLB and cache pollution.',
             'A context switch is when the CPU stops one process and starts another. It saves the registers '
             'and loads the new ones. It is expensive because of the overhead of saving and restoring state.'),
            ('Why does a thread context switch cost less than a process context switch?',
             'Threads share an address space, so switching between them does not require changing the page '
             'tables or flushing the TLB, only the register set.',
             'Threads share the same memory so the CPU does not need to change the memory map. Only the '
             'registers are swapped, which is faster.'),
        ],
    },
    {
        'title': 'DA2 - CPU Scheduling',
        'description': 'Assignment 2: scheduling algorithms and their trade-offs.',
        'delivery_mode': 'quiz',
        'due_in_days': None,
        'closes_in_days': None,
        'questions': [
            ('Compare FCFS and Round Robin scheduling.',
             'FCFS runs processes to completion in arrival order and suffers the convoy effect. Round Robin '
             'gives each process a time quantum, which improves response time at the cost of more context switches.',
             'FCFS runs in the order the processes arrive and waits till each finishes. Round Robin gives '
             'each process a fixed time slice and then moves to the next one.'),
            ('What is the convoy effect?',
             'Short processes queue behind one long CPU-bound process under FCFS, which inflates average '
             'waiting time.',
             'The convoy effect is when small processes are stuck waiting behind a big process that takes a '
             'long time, so everyone waits longer.'),
            ('What happens if the Round Robin time quantum is too small or too large?',
             'Too small and context-switch overhead dominates; too large and it degenerates into FCFS.',
             'If it is too small the CPU spends too much time switching. If it is too big it behaves like '
             'FCFS because each process finishes in one slice.'),
        ],
    },
    {
        'title': 'DA3 - Deadlocks and Synchronization',
        'description': 'Assignment 3: deadlock conditions and mutual exclusion. Upload one written sheet.',
        'delivery_mode': 'assignment',
        'due_in_days': 5,
        'closes_in_days': 14,
        'questions': [
            ('List the four necessary conditions for a deadlock.',
             'Mutual exclusion, hold and wait, no preemption, and circular wait.',
             'Mutual exclusion, hold and wait, no preemption and circular wait. All four must hold at the '
             'same time for a deadlock.'),
            ('How does a semaphore differ from a mutex?',
             'A mutex allows one holder and has ownership. A counting semaphore allows a fixed number of '
             'holders and has no ownership.',
             'A mutex is a lock that only one thread can hold. A semaphore has a counter so several threads '
             'can hold it, and it does not track who owns it.'),
            ('What is the critical section problem?',
             'Ensuring that when several processes share mutable state, no two execute their critical '
             'sections at the same time, while still guaranteeing progress and bounded waiting.',
             'The critical section problem is making sure two threads do not change shared data at the same '
             'time. We need mutual exclusion so the result stays correct.'),
        ],
    },
]


def get_or_create_user(name, email, role, password=DEFAULT_PASSWORD):
    """Find the account for `email`, creating it if it does not exist.

    The demo password is re-applied on every run rather than only at creation:
    the seeded credentials are printed as a way to log in, so they have to be
    true even when the account was already there with some other password.
    """
    user = User.query.filter_by(email=email).first()
    if user:
        user.name = name
        user.role = role
        user.set_password(password)
        db.session.commit()
        return user, False
    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, True


def get_or_create_class(teacher, name, description):
    group = ClassGroup.query.filter_by(teacher_id=teacher.id, name=name).first()
    if group:
        return group, False
    group = ClassGroup(teacher_id=teacher.id, name=name, description=description)
    db.session.add(group)
    db.session.commit()
    return group, True


def _apply_mode(set_obj, spec):
    """Write the seeded delivery mode and deadlines onto a set.

    `due_in_days` / `closes_in_days` are offsets from now: the soft due date
    after which work is still accepted but flagged late, and the hard close after
    which the link refuses everything. A `None` offset leaves that date unset.
    """
    set_obj.delivery_mode = spec['delivery_mode']
    now = datetime.utcnow()
    set_obj.due_at = now + timedelta(days=spec['due_in_days']) if spec['due_in_days'] else None
    set_obj.submissions_close_at = (now + timedelta(days=spec['closes_in_days'])
                                    if spec['closes_in_days'] else None)
    db.session.commit()


def seed(with_samples=True):
    teacher, teacher_created = get_or_create_user(TEACHER_NAME, TEACHER_EMAIL, 'teacher')

    classes = {}
    students_by_class = {}
    for class_name, description in CLASSES.items():
        group, _ = get_or_create_class(teacher, class_name, description)
        classes[class_name] = group
        students_by_class[class_name] = []
        for name, email in STUDENTS[class_name]:
            student, _ = get_or_create_user(name, email, 'student')
            if student not in group.members:
                group.members.append(student)
            students_by_class[class_name].append(student)
        db.session.commit()

    sets = []
    for index, spec in enumerate(ASSIGNMENTS):
        set_obj = Set.query.filter_by(teacher_id=teacher.id, title=spec['title']).first()
        if not set_obj:
            set_obj = Set(teacher_id=teacher.id, title=spec['title'],
                          description=spec['description'], book_mode='open_book')
            db.session.add(set_obj)
            db.session.commit()
            for question_text, ideal_answer, _ in spec['questions']:
                db.session.add(Question(set_id=set_obj.id, question_text=question_text,
                                        ideal_answer=ideal_answer, max_score=10, strictness=3))
            db.session.commit()

        # The seeded sets are a fixture, so the mode and deadlines are re-applied
        # on every run: a database seeded before these columns existed has to end
        # up looking like a freshly seeded one.
        _apply_mode(set_obj, spec)
        # The paper students answer against is written from the questions, so a
        # freshly seeded set is complete without opening it in the browser first.
        sync_question_paper(set_obj)
        sets.append(set_obj)

        # Grant both slots access so every student can see the assignment.
        for group in classes.values():
            for student in group.members:
                grant = AccessGrant.query.filter_by(student_id=student.id, set_id=set_obj.id).first()
                if not grant:
                    db.session.add(AccessGrant(student_id=student.id, set_id=set_obj.id,
                                               class_group_id=group.id, max_attempts=2))
        db.session.commit()

    sample_count = 0
    if with_samples:
        sample_count = _seed_samples(sets, students_by_class)

    return {
        'teacher_created': teacher_created,
        'students': sum(len(v) for v in students_by_class.values()),
        'sets': len(sets),
        'samples': sample_count,
    }


def _seed_samples(sets, students_by_class):
    """Grade a plausible answer from each student with the AI switched off.

    Local-only so seeding is instant and never burns API quota.
    """
    validator = AnswerValidator()
    validator.client = None  # force the offline grading paths

    # Stagger timestamps so the mark sheet has a sensible "latest attempt" order.
    base_time = datetime.utcnow() - timedelta(days=7)
    written = 0

    for set_index, set_obj in enumerate(sets):
        spec = ASSIGNMENTS[set_index]
        questions = Question.query.filter_by(set_id=set_obj.id).order_by(Question.id).all()
        for class_name, students in students_by_class.items():
            for student_index, student in enumerate(students):
                already = db.session.query(Log).join(Question, Log.question_id == Question.id).filter(
                    Question.set_id == set_obj.id, Log.student_id == student.id
                ).first()

                if not already:
                    for position, question in enumerate(questions):
                        if position >= len(spec['questions']):
                            break
                        _, ideal_answer, sample_answer = spec['questions'][position]
                        result = validator._validate_with_similarity(
                            question.question_text, sample_answer, ideal_answer, question.strictness
                        )
                        db.session.add(Log(
                            student_id=student.id,
                            question_id=question.id,
                            answer=sample_answer,
                            ai_response=result['explanation'],
                            score=result['score'],
                            max_score=result['max_score'],
                            source_used=result['source_used'],
                            confidence=result['confidence'],
                            key_point=result['key_point'],
                            attempt_no=1,
                            timestamp=base_time
                            + timedelta(days=set_index * 2, hours=student_index),
                        ))
                        written += 1

                # The sample answers are attempt 1 as far as the mark sheet is
                # concerned, so spend an attempt on the grant. Without this the
                # student's own first attempt would also be numbered 1 and the
                # two papers would be added together. Guarded by `< 1` so an
                # account that already has real attempts is left alone.
                grant = AccessGrant.query.filter_by(student_id=student.id,
                                                    set_id=set_obj.id).first()
                if grant and grant.attempts_used < 1:
                    grant.attempts_used = 1
                db.session.commit()
    return written


def main():
    parser = argparse.ArgumentParser(description='Seed the grading system with a demo class.')
    parser.add_argument('--no-samples', action='store_true',
                        help='skip the sample submissions and create accounts only')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        summary = seed(with_samples=not args.no_samples)

    print('Seed complete.')
    print(f"  teacher:  {TEACHER_EMAIL} / {DEFAULT_PASSWORD}")
    print(f"  classes:  {', '.join(CLASSES)}")
    print(f"  students: {summary['students']} ({summary['students'] // len(CLASSES)} per class)")
    print(f"  sets:     {summary['sets']} assignments")
    if args.no_samples:
        print('  samples:  skipped')
    else:
        print(f"  samples:  {summary['samples']} graded answers, marked by the local grader")


if __name__ == '__main__':
    main()
