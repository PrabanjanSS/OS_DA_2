"""Per-student question allocation from a generated question pool.

The problem this solves is a resource-allocation one: a set holds a pool of
questions and every student wants `questions_per_student` of them at once. If
two students start their attempt at the same moment they should not be handed
the same questions, so the allocate step runs under a lock and picks the
questions that are currently in the fewest hands.

A hard guarantee ("no two students ever share a question") is only possible if
the pool is large enough to cover every student at once. When it is not, this
degrades to the least-used question rather than refusing to hand out a paper.
"""
import random
from typing import List

from sqlalchemy import and_, func

from extensions import db
from models import AccessGrant, Question, QuestionAllocation
from services.concurrency import allocation_lock


def _question_ids_for_set(set_id: int) -> List[int]:
    rows = db.session.query(Question.id).filter(Question.set_id == set_id).all()
    return [row[0] for row in rows]


def _open_usage(set_id: int) -> dict:
    """How many students hold each question in an attempt that is still open."""
    rows = db.session.query(
        QuestionAllocation.question_id, func.count(QuestionAllocation.id)
    ).join(
        AccessGrant,
        and_(AccessGrant.student_id == QuestionAllocation.student_id,
             AccessGrant.set_id == QuestionAllocation.set_id),
    ).filter(
        QuestionAllocation.set_id == set_id,
        AccessGrant.attempt_started_at.isnot(None),
    ).group_by(QuestionAllocation.question_id).all()
    return {question_id: count for question_id, count in rows}


def _total_usage(set_id: int) -> dict:
    """Lifetime allocation count per question, used to even out the spread."""
    rows = db.session.query(
        QuestionAllocation.question_id, func.count(QuestionAllocation.id)
    ).filter(
        QuestionAllocation.set_id == set_id
    ).group_by(QuestionAllocation.question_id).all()
    return {question_id: count for question_id, count in rows}


def _rank(question_id, open_usage, total_usage):
    # Fewest hands first, then the least-used overall, then chance.
    return (open_usage.get(question_id, 0), total_usage.get(question_id, 0), random.random())


def allocate_questions(set_obj, student_id: int, attempt_no: int) -> List[Question]:
    """Hand `student_id` their questions for one attempt, and remember which.

    Returns the questions in the order the student should see them.
    """
    needed = set_obj.questions_per_student or 1
    question_ids = _question_ids_for_set(set_obj.id)
    if not question_ids:
        return []

    with allocation_lock:
        # Already handed this student their paper for this attempt? Keep it, so a
        # page refresh cannot reshuffle the questions underneath them.
        existing = QuestionAllocation.query.filter_by(
            student_id=student_id, set_id=set_obj.id, attempt_no=attempt_no
        ).order_by(QuestionAllocation.position).all()
        if existing:
            by_id = {q.id: q for q in Question.query.filter(Question.id.in_(question_ids)).all()}
            return [by_id[a.question_id] for a in existing if a.question_id in by_id]

        seen = {
            row[0] for row in db.session.query(QuestionAllocation.question_id).filter_by(
                student_id=student_id, set_id=set_obj.id
            ).all()
        }
        open_usage = _open_usage(set_obj.id)
        total_usage = _total_usage(set_obj.id)

        # Fresh questions first; only repeat from a previous attempt if the pool
        # is too small to fill this paper otherwise.
        fresh = [qid for qid in question_ids if qid not in seen]
        repeat = [qid for qid in question_ids if qid in seen]
        fresh.sort(key=lambda qid: _rank(qid, open_usage, total_usage))
        repeat.sort(key=lambda qid: _rank(qid, open_usage, total_usage))

        chosen = (fresh + repeat)[:needed]
        # The order students see them in is independent of the pick, so two
        # students given the same pair still do not see it in the same order.
        random.shuffle(chosen)

        for position, question_id in enumerate(chosen):
            db.session.add(QuestionAllocation(
                student_id=student_id,
                set_id=set_obj.id,
                question_id=question_id,
                attempt_no=attempt_no,
                position=position,
            ))
        db.session.commit()

    by_id = {q.id: q for q in Question.query.filter(Question.id.in_(chosen)).all()}
    return [by_id[qid] for qid in chosen if qid in by_id]


def allocated_questions(student_id: int, set_id: int, attempt_no: int) -> List[Question]:
    """Read back a student's allocation for one attempt, in the set order."""
    rows = QuestionAllocation.query.filter_by(
        student_id=student_id, set_id=set_id, attempt_no=attempt_no
    ).order_by(QuestionAllocation.position).all()
    if not rows:
        return []
    wanted = [row.question_id for row in rows]
    by_id = {q.id: q for q in Question.query.filter(Question.id.in_(wanted)).all()}
    return [by_id[qid] for qid in wanted if qid in by_id]
