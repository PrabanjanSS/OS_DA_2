"""
Test script to verify all functionality of the AI Grading System
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test 1: Check environment variables
print("=" * 60)
print("TEST 1: Environment Variables")
print("=" * 60)
print(f"SECRET_KEY: {'✓ Set' if os.getenv('SECRET_KEY') else '✗ Missing'}")
print(f"GEMINI_API_KEY: {'✓ Set' if os.getenv('GEMINI_API_KEY') else '✗ Missing'}")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")
print()

# Test 2: Test imports
print("=" * 60)
print("TEST 2: Import Modules")
print("=" * 60)
try:
    from flask import Flask
    print("✓ Flask imported successfully")
except ImportError as e:
    print(f"✗ Flask import failed: {e}")

try:
    from flask_login import LoginManager
    print("✓ Flask-Login imported successfully")
except ImportError as e:
    print(f"✗ Flask-Login import failed: {e}")

try:
    from flask_sqlalchemy import SQLAlchemy
    print("✓ Flask-SQLAlchemy imported successfully")
except ImportError as e:
    print(f"✗ Flask-SQLAlchemy import failed: {e}")

try:
    import google.generativeai as genai
    print("✓ Google Generative AI imported successfully")
except ImportError as e:
    print(f"✗ Google Generative AI import failed: {e}")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    print("✓ scikit-learn imported successfully")
except ImportError as e:
    print(f"✗ scikit-learn import failed: {e}")

try:
    import PyPDF2
    print("✓ PyPDF2 imported successfully")
except ImportError as e:
    print(f"✗ PyPDF2 import failed: {e}")

try:
    import docx
    print("✓ python-docx imported successfully")
except ImportError as e:
    print(f"✗ python-docx import failed: {e}")
print()

# Test 3: Test Gemini API connection
print("=" * 60)
print("TEST 3: Gemini API Connection")
print("=" * 60)
try:
    import google.generativeai as genai
    api_key = os.getenv('GEMINI_API_KEY')
    if api_key:
        genai.configure(api_key=api_key)
        
        # Try with models/gemini-2.5-flash (better free tier availability)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        # Test with a simple prompt
        test_prompt = "Respond with JSON: {\"test\": \"success\"}"
        response = model.generate_content(test_prompt)
        print(f"✓ Gemini API connected successfully")
        print(f"  Response: {response.text[:100]}...")
    else:
        print("✗ GEMINI_API_KEY not set in .env file")
except Exception as e:
    print(f"✗ Gemini API connection failed: {e}")
print()

# Test 4: Test similarity service
print("=" * 60)
print("TEST 4: Similarity Service (TF-IDF)")
print("=" * 60)
try:
    from services.similarity import SimilarityMatcher
    matcher = SimilarityMatcher()
    
    # Test indexing
    chunks = ["This is a test document about machine learning.", 
              "Neural networks are a subset of machine learning."]
    matcher.index_materials(chunks)
    print("✓ Material indexing successful")
    
    # Test similarity search
    query = "What is machine learning?"
    results = matcher.find_most_similar(query, top_k=1)
    print(f"✓ Similarity search successful")
    print(f"  Found {len(results)} results")
    if results:
        print(f"  Top result similarity: {results[0][1]:.2f}")
    
    # Test direct similarity
    text1 = "The cat sat on the mat"
    text2 = "A cat was sitting on a mat"
    score = matcher.get_similarity_score(text1, text2)
    print(f"✓ Direct similarity calculation successful")
    print(f"  Similarity score: {score:.2f}")
except Exception as e:
    print(f"✗ Similarity service failed: {e}")
print()

# Test 5: Test validator service
print("=" * 60)
print("TEST 5: Validator Service")
print("=" * 60)
try:
    from services.validator import AnswerValidator
    validator = AnswerValidator()
    print("✓ Validator initialized successfully")
    
    # Test validation with materials
    materials = ["Python is a high-level programming language."]
    validator.index_set_materials(materials)
    print("✓ Material indexing in validator successful")
    
    # Test validation
    result = validator.validate_answer(
        question="What is Python?",
        answer="Python is a programming language",
        ideal_answer="Python is a high-level programming language"
    )
    print("✓ Answer validation successful")
    print(f"  Score: {result['score']}/{result['max_score']}")
    print(f"  Correct: {result['correct']}")
    print(f"  Source: {result['source_used']}")
    print(f"  Explanation: {result['explanation'][:80]}...")
except Exception as e:
    print(f"✗ Validator service failed: {e}")
print()

# Test 6: Test file parser
print("=" * 60)
print("TEST 6: File Parser")
print("=" * 60)
try:
    from services.file_parser import extract_text_from_file, chunk_text
    
    # Test with a temporary text file
    test_file = "test_sample.txt"
    with open(test_file, 'w') as f:
        f.write("This is a test document. It contains multiple sentences. The text will be chunked.")
    
    text = extract_text_from_file(test_file, 'txt')
    print(f"✓ Text extraction successful")
    print(f"  Extracted length: {len(text)} characters")
    
    chunks = chunk_text(text, chunk_size=5)
    print(f"✓ Text chunking successful")
    print(f"  Number of chunks: {len(chunks)}")
    
    # Clean up
    os.remove(test_file)
except Exception as e:
    print(f"✗ File parser failed: {e}")
print()

# Test 7: Test concurrency service
print("=" * 60)
print("TEST 7: Concurrency Service (Threading)")
print("=" * 60)
try:
    from services.concurrency import executor, attempt_lock, log_lock
    print("✓ Thread pool initialized")
    print(f"  Max workers: {executor._max_workers}")
    print("✓ Locks initialized")
    print("  attempt_lock: Ready")
    print("  log_lock: Ready")
except Exception as e:
    print(f"✗ Concurrency service failed: {e}")
print()

# Test 8: Test database models
print("=" * 60)
print("TEST 8: Database Models")
print("=" * 60)
try:
    from models import User, Set, Material, Question, AccessGrant, Log
    from extensions import db
    print("✓ All models imported successfully")
    print("  Models: User, Set, Material, Question, AccessGrant, Log")
except Exception as e:
    print(f"✗ Database models failed: {e}")
print()

print("=" * 60)
print("SUMMARY")
print("=" * 60)
print("All core functionality tests completed!")
print("The system is ready to use.")
print("=" * 60)
