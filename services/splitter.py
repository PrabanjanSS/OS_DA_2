"""Cut one uploaded answer sheet back into per-question answers.

A file-based assignment has the student write every answer into a single
Word/PDF document. Grading happens per question, so the sheet has to be split
into one section per question first. The language model does this well when it
is reachable; a marker-based heuristic covers the offline case so a submission
is never rejected just because the API is down.
"""
import json
import re
from typing import Dict, List, Optional

import google.generativeai as genai

from config import Config
from services.generator import _close_truncated_json

# Markers students actually use in a written sheet: "Q3", "Question 3.",
# "3.", "3)", "Ans 3 -" and the like, at the start of a line. A "Question 3"
# heading counts even without trailing punctuation, since that is how a paper
# exported from this app labels its own questions.
_MARKER = re.compile(
    r'(?im)^[ \t>*_-]*(?:(?:q(?:uestion)?|ans(?:wer)?)\s*(\d{1,2})\s*[.):\-]?|(\d{1,2})\s*[.):\-])\s*'
)

_METHOD_LABELS = {
    'ai': 'Split by the AI',
    'markers': "Split on the sheet's own question numbers",
    'paragraphs': 'Split into paragraphs, one per question',
    'whole': 'No question structure found, so the sheet was kept whole',
}


def _extract_answer_map(response_text: str, count: int) -> Dict[int, str]:
    """Pull `{question number: answer}` out of an AI response.

    Accepts the documented `{"answers": [{"n": .., "text": ..}]}` shape as well
    as a bare list, and tolerates markdown fences and a truncated tail.
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
        try:
            payload = json.loads(_close_truncated_json(text))
        except json.JSONDecodeError:
            return {}

    if isinstance(payload, dict):
        payload = payload.get('answers') or payload.get('parts') or []
    if not isinstance(payload, list):
        return {}

    parts = {}
    for position, item in enumerate(payload):
        if isinstance(item, str):
            item = {'n': position + 1, 'text': item}
        if not isinstance(item, dict):
            continue
        raw_number = item.get('n', item.get('number', position + 1))
        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            continue
        if number < 1 or number > count:
            continue
        parts[number] = (item.get('text') or item.get('answer') or '').strip()
    return parts


def _split_with_ai(text: str, question_texts: List[str]) -> Dict[int, str]:
    """Ask the model to split the sheet. Returns {} when it is unavailable."""
    if not Config.GEMINI_API_KEY:
        return {}

    listing = '\n'.join(f'{i + 1}. {q}' for i, q in enumerate(question_texts))
    prompt = f"""A student wrote their answers to the questions below into one document. Split the document back into one answer per question.

Questions:
{listing}

The student's document:
\"\"\"
{text}
\"\"\"

Return ONLY a JSON object in this exact format:
{{
    "answers": [
        {{"n": 1, "text": "<exactly what the student wrote for question 1, verbatim>"}}
    ]
}}
Include every question from 1 to {len(question_texts)}. Use an empty string for a question the student did not attempt. Do not add commentary before or after the JSON.
"""

    try:
        genai.configure(api_key=Config.GEMINI_API_KEY)
        model = genai.GenerativeModel(Config.GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=8192,
            ),
        )
        return _extract_answer_map(response.text or '', len(question_texts))
    except Exception as exc:  # network, quota, malformed JSON: fall back to markers
        print(f'Answer-sheet split failed, falling back to markers: {exc}')
        return {}


def _split_by_markers(text: str, count: int) -> Dict[int, str]:
    """Cut the sheet at the question numbers the student wrote themselves."""
    matches = list(_MARKER.finditer(text))
    if not matches:
        return {}

    parts: Dict[int, str] = {}
    for index, match in enumerate(matches):
        number = int(match.group(1) or match.group(2))
        if number < 1 or number > count:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        # The same number can appear twice (a list at the top, the answer below);
        # keep both rather than losing either half.
        parts[number] = f'{parts[number]}\n{body}'.strip() if number in parts else body
    return parts


def _split_by_paragraphs(text: str, count: int) -> Dict[int, str]:
    """Last resort: an unlabelled sheet with exactly one block per question."""
    blocks = [block.strip() for block in re.split(r'\n\s*\n', text) if block.strip()]
    if len(blocks) != count:
        return {}
    return {index + 1: block for index, block in enumerate(blocks)}


def split_answer_sheet(text: str, questions: List) -> Dict:
    """Map one written sheet onto its questions.

    `questions` is the ordered list of Question rows the student was given.
    Returns {'answers': {question_id: answer}, 'method': str, 'note': str}; the
    answers map always has an entry for every question, empty when the student
    left that one out.
    """
    count = len(questions)
    if not text or not text.strip() or count == 0:
        return {'answers': {}, 'method': 'none',
                'note': 'The uploaded document had no readable text.'}

    if count == 1:
        parts = {1: text.strip()}
        method = 'whole'
    else:
        parts = _split_with_ai(text, [q.question_text for q in questions])
        method = 'ai' if parts else ''
        if not parts:
            parts = _split_by_markers(text, count)
            method = 'markers' if parts else ''
        if not parts:
            parts = _split_by_paragraphs(text, count)
            method = 'paragraphs' if parts else ''
        if not parts:
            # Structure could not be guessed; grade the whole sheet against the
            # first question rather than discarding the student's work.
            parts = {1: text.strip()}
            method = 'whole'

    answers = {}
    matched = 0
    for index, question in enumerate(questions):
        body = (parts.get(index + 1) or '').strip()
        answers[question.id] = body
        if body:
            matched += 1

    note = f'{_METHOD_LABELS[method]}. {matched} of {count} answers located.'
    return {'answers': answers, 'method': method, 'note': note}
