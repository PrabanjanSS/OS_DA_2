"""
Test with the user's actual answers to show AI grading
"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from models import db, User, Set, Question, Log
from services.validator import AnswerValidator
from services.file_parser import chunk_text

def test_your_answers():
    """Test with the user's actual answers from the screenshot"""
    
    app = create_app()
    
    with app.app_context():
        print("=" * 70)
        print("TESTING YOUR ACTUAL ANSWERS WITH GEMINI API")
        print("=" * 70)
        print()
        
        # Find the student
        student = User.query.filter_by(email='jane.student@test.com').first()
        if not student:
            print("❌ Student jane.student@test.com not found")
            print("Please check the email address")
            return False
        
        print(f"✓ Found student: {student.name}")
        print()
        
        # Find the most recent question set
        question_set = Set.query.order_by(Set.id.desc()).first()
        if not question_set:
            print("❌ No question sets found")
            return False
        
        print(f"✓ Found question set: {question_set.title}")
        print()
        
        # Initialize validator with set materials
        validator = AnswerValidator()
        materials = [m.processed_text for m in question_set.materials if m.processed_text]
        if materials:
            validator.index_set_materials(materials)
            print(f"✓ Validator indexed {len(materials)} material(s)")
        print()
        
        # Your actual answers from the screenshot
        your_answers = [
            {
                "question": "How do you define a function in Python? Provide an example.",
                "answer": "Functions are defined using the def keyword. For example: def my_function(param): return param * 2. This creates a reusable block of code."
            },
            {
                "question": "How do you create a list in Python and what are two common list operations?",
                "answer": "Lists in Python are created using square brackets. For example: fruits = [\"apple\", \"banana\"]. Two common operations are append() to add items and remove() to delete items."
            },
            {
                "question": "What are the four basic data types in Python and give an example of each?",
                "answer": "The four basic data types in Python are int for whole numbers like 42, float for decimal numbers like 3.14, str for text strings like \"Hello\", and bool for boolean values True and False."
            }
        ]
        
        print("=" * 70)
        print("GRADING YOUR ANSWERS WITH GEMINI API (12s delay between each)")
        print("=" * 70)
        print()
        
        total_score = 0
        max_total = 0
        
        for i, ans_data in enumerate(your_answers):
            print(f"Question {i+1}:")
            print(f"  {ans_data['question']}")
            print(f"\nYour Answer:")
            print(f"  {ans_data['answer']}")
            print()
            
            # Validate with delay for API quota
            print("  Validating with Gemini API...")
            result = validator.validate_answer(
                ans_data['question'],
                ans_data['answer'],
                None  # No ideal answer
            )
            
            total_score += result['score']
            max_total += result['max_score']
            
            print(f"  ✅ Score: {result['score']}/{result['max_score']}")
            print(f"  ✅ Correct: {result['correct']}")
            print(f"  ✅ Source: {result['source_used']}")
            print(f"  ✅ Confidence: {result['confidence']}")
            print(f"  ✅ Explanation: {result['explanation'][:200]}...")
            print()
            
            # Wait for API quota
            if i < len(your_answers) - 1:
                print("  ⏳ Waiting 12 seconds for API quota...")
                time.sleep(12)
                print()
        
        print("=" * 70)
        print("COMPARISON: Your Screenshot vs AI Grading")
        print("=" * 70)
        print()
        print("Your Screenshot (Fallback Mode):")
        print("  Q1 (Functions): 2.3/10 - Material Match")
        print("  Q2 (Lists): 7.3/10 - Fallback Dataset")
        print("  Q3 (Data Types): 2.3/10 - Material Match")
        print("  Total: ~12/30 (40%)")
        print()
        print("With Gemini API (This Test):")
        print(f"  Total: {total_score}/{max_total} ({(total_score/max_total)*100:.1f}%)")
        print()
        
        if total_score > 20:
            print("✅ SUCCESS: Your answers are actually GOOD!")
            print("   The issue was using fallback mode instead of AI.")
        else:
            print("⚠️  Still showing issues with API grading")
        
        print("=" * 70)
        
        return True

if __name__ == '__main__':
    try:
        success = test_your_answers()
        if success:
            print("\n✅ Test completed!")
            sys.exit(0)
        else:
            print("\n❌ Test failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
