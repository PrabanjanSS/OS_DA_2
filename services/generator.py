"""AI question-pool generation.

A teacher supplies a topic, how many questions each student should answer, a
difficulty and optional notes; this module asks Gemini for a larger pool of
questions on that topic. The pool is stored on the set and handed out per
student by services.allocation.
"""
import json
import time
from typing import Dict, List, Optional

import google.generativeai as genai

from config import Config

# Question difficulty, mirroring the 1-5 shape of the grading strictness levels.
DIFFICULTY_LEVELS = {
    1: ('Very easy', 'Ask for a single fact or definition that any student who attended the lecture could recall.'),
    2: ('Easy', 'Ask a short recall question covering one concept from the topic.'),
    3: ('Moderate', 'Ask a question that requires explaining a concept and why it works.'),
    4: ('Hard', 'Ask a question that requires comparing concepts or applying them to a scenario.'),
    5: ('Very hard', 'Ask a question that requires reasoning across several concepts, edge cases or trade-offs.'),
}
DEFAULT_DIFFICULTY = 3

# Guard rails so a typo in the form cannot ask the model for 500 questions.
MIN_PER_STUDENT = 1
MAX_PER_STUDENT = 5
MAX_POOL = 30


def difficulty_profile(difficulty) -> tuple:
    """Clamp a difficulty to a known level: (label, instruction)."""
    try:
        level = int(difficulty)
    except (TypeError, ValueError):
        level = DEFAULT_DIFFICULTY
    level = min(max(level, 1), 5)
    return DIFFICULTY_LEVELS[level]


def _close_truncated_json(text: str) -> str:
    """Close the brackets and strings a response was cut off in the middle of.

    A thinking model can stop mid-answer, leaving something like
    `{"questions": [{"question": "..."}]` with no closing brace. Closing them
    naively in the wrong order produces JSON that parses no better than the
    original, so the unclosed openers are tracked and closed innermost-first.
    """
    out = text
    stack = []
    in_string = False
    escaped = False

    for ch in out:
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in '{[':
            stack.append(ch)
        elif ch in '}]' and stack:
            stack.pop()

    if in_string:
        out += '"'
    for opener in reversed(stack):
        out += ']' if opener == '[' else '}'
    return out


def _extract_questions(response_text: str) -> List[Dict]:
    """Pull a list of question objects out of an AI response.

    Accepts either a bare JSON array or an object containing one, tolerating the
    markdown fences and truncated payloads that the grading prompt also suffers
    from.
    """
    text = (response_text or '').strip()

    if '```' in text:
        block = text[text.find('```') + 3:]
        if '\n' in block:
            block = block.split('\n', 1)[1]  # drop the "json" language hint
        end = block.find('```')
        text = (block[:end] if end != -1 else block).strip()

    payload = None
    for candidate in (text, text[text.find('['):text.rfind(']') + 1],
                      text[text.find('{'):text.rfind('}') + 1]):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue

    if payload is None:
        # Likely truncated mid-array: close the dangling structures and retry.
        try:
            payload = json.loads(_close_truncated_json(text))
        except json.JSONDecodeError:
            raise ValueError('No JSON found in the question-generation response')

    if isinstance(payload, dict):
        payload = payload.get('questions') or []
    if not isinstance(payload, list):
        raise ValueError('Question-generation response was not a list')

    questions = []
    for item in payload:
        if isinstance(item, str):
            item = {'question': item}
        if not isinstance(item, dict):
            continue
        text_value = (item.get('question') or item.get('question_text') or '').strip()
        if not text_value:
            continue
        questions.append({
            'question': text_value,
            'ideal_answer': (item.get('ideal_answer') or item.get('answer') or '').strip() or None,
        })
    return questions


def generate_question_pool(topic: str, per_student: int, difficulty: int = DEFAULT_DIFFICULTY,
                           pool_size: Optional[int] = None, notes: str = '',
                           context: str = '') -> Dict:
    """Ask Gemini for a pool of questions on `topic`.

    `per_student` is how many questions each student will ultimately answer; the
    pool is deliberately larger so allocations can differ between students.
    Returns {'questions': [...], 'error': None} or {'questions': [], 'error': str}.
    """
    topic = (topic or '').strip()
    if not topic:
        return {'questions': [], 'error': 'Enter a topic before generating questions.'}

    if not Config.GEMINI_API_KEY:
        return {'questions': [], 'error': 'Question generation needs GEMINI_API_KEY to be set.'}

    try:
        per_student = int(per_student)
    except (TypeError, ValueError):
        per_student = MIN_PER_STUDENT
    per_student = min(max(per_student, MIN_PER_STUDENT), MAX_PER_STUDENT)

    if pool_size is None:
        # Three questions in the pool for every one a student answers gives the
        # allocator room to keep neighbours apart.
        pool_size = per_student * 3
    try:
        pool_size = int(pool_size)
    except (TypeError, ValueError):
        pool_size = per_student * 3
    pool_size = min(max(pool_size, per_student), MAX_POOL)

    label, instruction = difficulty_profile(difficulty)

    prompt = f"""You are writing a question pool for an exam on: {topic}

Write {pool_size} distinct questions on this topic. Each student will be given
{per_student} of them at random, so the questions must be interchangeable in
difficulty and must NOT be variants of the same sentence.

Difficulty: {label}. {instruction}
"""
    if notes:
        prompt += f"""
Additional instructions from the teacher (follow these closely):
{notes}
"""
    if context:
        prompt += f"""
Base the questions on this course material:
{context}
"""

    prompt += """
Respond ONLY with a JSON object in this exact format:
{
    "questions": [
        {
            "question": "<the question text>",
            "ideal_answer": "<a concise model answer used for grading, under 40 words>"
        }
    ]
}
Do not add commentary before or after the JSON.
"""

    try:
        genai.configure(api_key=Config.GEMINI_API_KEY)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.9,  # a pool that reads as one voice defeats the point
                # Room for the whole pool plus the model's thinking tokens; too
                # small a budget truncates the JSON mid-item.
                max_output_tokens=8192,
            ),
        )
        questions = _extract_questions(response.text or '')
    except Exception as exc:  # network, quota, malformed JSON - all reported the same way
        return {'questions': [], 'error': f'Question generation failed: {exc}'}

    if not questions:
        return {'questions': [], 'error': 'The model returned no usable questions. Try again.'}

    return {'questions': questions[:pool_size], 'error': None}
