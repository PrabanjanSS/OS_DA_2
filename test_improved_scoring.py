"""
Test improved scoring with local fallback
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from services.validator import AnswerValidator
from services.file_parser import chunk_text

# Sample material content
material_content = """
Python Programming Basics

Python is a high-level, interpreted programming language known for its simplicity 
and readability. It supports multiple programming paradigms including procedural, 
object-oriented, and functional programming.

Key Features:
- Dynamic typing
- Automatic memory management
- Extensive standard library
- Cross-platform compatibility

Variables in Python:
Variables are created when you assign a value to them. Python uses dynamic typing, 
so you don't need to declare variable types.

Example:
x = 5
name = "Alice"
is_valid = True

Functions:
Functions are defined using the 'def' keyword. They can take parameters and 
return values.

Example:
def greet(name):
    return f"Hello, {name}!"

Lists:
Lists are ordered, mutable collections in Python.
numbers = [1, 2, 3, 4, 5]
names = ["Alice", "Bob", "Charlie"]
"""

print("=" * 70)
print("TEST: Improved Local Scoring (Fallback Mode)")
print("=" * 70)
print()

# Initialize validator WITHOUT API (to test fallback)
from config import Config
Config.GEMINI_API_KEY = None  # Disable API to test fallback

validator = AnswerValidator()
print("✓ Validator initialized (API disabled for fallback test)")
print()

# Index the material
chunks = chunk_text(material_content, chunk_size=500)
validator.index_set_materials([material_content])
print(f"✓ Material indexed with {len(chunks)} chunks")
print()

# Test with good answer
print("-" * 70)
print("Test 1: Good Answer (Local Fallback)")
print("-" * 70)
question = "What is Python and what are its key features?"
answer = "Python is a high-level programming language with dynamic typing and automatic memory management."
ideal_answer = "Python is a high-level, interpreted programming language. Key features include dynamic typing, automatic memory management, extensive standard library, and cross-platform compatibility."

result = validator.validate_answer(question, answer, ideal_answer)
print(f"Score: {result['score']}/{result['max_score']}")
print(f"Correct: {result['correct']}")
print(f"Source: {result['source_used']}")
print(f"Confidence: {result['confidence']}")
print(f"Explanation: {result['explanation']}")
print()

# Test with moderate answer
print("-" * 70)
print("Test 2: Moderate Answer (Local Fallback)")
print("-" * 70)
question2 = "How do you define a function in Python?"
answer2 = "You use def to make a function"
ideal_answer2 = "Functions are defined using the 'def' keyword. Example: def greet(name): return f'Hello, {name}!'"

result2 = validator.validate_answer(question2, answer2, ideal_answer2)
print(f"Score: {result2['score']}/{result2['max_score']}")
print(f"Correct: {result2['correct']}")
print(f"Source: {result2['source_used']}")
print(f"Confidence: {result2['confidence']}")
print(f"Explanation: {result2['explanation']}")
print()

print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Test 1 Score: {result['score']}/10 (was ~2.3/10 before fix)")
print(f"Test 2 Score: {result2['score']}/10 (was ~7.3/10 before fix)")
print()
if result['score'] > 3 and result2['score'] > 3:
    print("✅ SUCCESS: Improved scoring working better!")
else:
    print("⚠️  WARNING: Scores still low")
print("=" * 70)
