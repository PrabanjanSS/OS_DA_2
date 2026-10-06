"""
Test that Gemini API is being used with material context
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from services.validator import AnswerValidator
from services.file_parser import chunk_text

# Sample material content (simulating uploaded teacher material)
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
print("TEST: Gemini API with Material Context")
print("=" * 70)
print()

# Initialize validator
validator = AnswerValidator()
print("✓ Validator initialized")
print(f"  Gemini API client: {'Connected' if validator.client else 'Not connected'}")
print()

# Index the material
chunks = chunk_text(material_content, chunk_size=500)
validator.index_set_materials([material_content])
print(f"✓ Material indexed with {len(chunks)} chunks")
print()

# Test validation with a good answer
print("-" * 70)
print("Test 1: Good Answer (should use AI API with context)")
print("-" * 70)
question = "What is Python and what are its key features?"
answer = "Python is a high-level, interpreted programming language known for simplicity and readability. Its key features include dynamic typing, automatic memory management, extensive standard library, and cross-platform compatibility."
ideal_answer = "Python is a high-level, interpreted programming language. Key features include dynamic typing, automatic memory management, extensive standard library, and cross-platform compatibility."

result = validator.validate_answer(question, answer, ideal_answer)
print(f"Score: {result['score']}/{result['max_score']}")
print(f"Correct: {result['correct']}")
print(f"Source: {result['source_used']}")
print(f"Confidence: {result['confidence']}")
print(f"Explanation: {result['explanation']}")
print()

# Test validation with a poor answer
print("-" * 70)
print("Test 2: Poor Answer (should use AI API with context)")
print("-" * 70)
question2 = "How do you define a function in Python?"
answer2 = "I don't know how to define functions."
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
print(f"Test 1 Source: {result['source_used']}")
print(f"Test 2 Source: {result2['source_used']}")
print()
if result['source_used'] == 'ai_api' and result2['source_used'] == 'ai_api':
    print("✅ SUCCESS: Both validations used Gemini API with material context!")
else:
    print("⚠️  WARNING: Not using Gemini API as expected")
print("=" * 70)
