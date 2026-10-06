"""
Simulate student submission with good, average, and bad answers
to test API grading with material context
"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from models import db, User, Set, Question, AccessGrant, Log
from services.validator import AnswerValidator
from services.file_parser import chunk_text
from werkzeug.security import generate_password_hash

def test_student_submission():
    """Test student submission with varied answer quality"""
    
    app = create_app()
    
    with app.app_context():
        print("=" * 70)
        print("STUDENT SUBMISSION TEST - API GRADING WITH CONTEXT")
        print("=" * 70)
        print()
        
        # Find the student
        student = User.query.filter_by(email='john.student@test.com').first()
        if not student:
            print("❌ Student john.student@test.com not found")
            print("Creating student account...")
            student = User(
                name="John Student",
                email="john.student@test.com",
                password_hash=generate_password_hash("student123"),
                role="student"
            )
            db.session.add(student)
            db.session.commit()
            print("✓ Student account created")
        else:
            print(f"✓ Found student: {student.name}")
        print()
        
        # Find the most recent question set
        question_set = Set.query.order_by(Set.id.desc()).first()
        if not question_set:
            print("❌ No question sets found")
            return False
        
        print(f"✓ Found question set: {question_set.title}")
        print(f"  Questions: {len(question_set.questions)}")
        print(f"  Materials: {len(question_set.materials)}")
        print()
        
        # Initialize validator with set materials
        validator = AnswerValidator()
        materials = [m.processed_text for m in question_set.materials if m.processed_text]
        if materials:
            validator.index_set_materials(materials)
            print(f"✓ Validator indexed {len(materials)} material(s)")
        else:
            print("⚠️  No materials found, will use fallback")
        print()
        
        # Get questions
        questions = question_set.questions
        if len(questions) < 3:
            print("⚠️  Less than 3 questions found")
        
        # Test answers: Good, Average, Bad (matching actual questions)
        test_answers = []
        
        for i, question in enumerate(questions):
            if i == 0:
                # Question about data types
                test_answers.append({
                    "type": "GOOD",
                    "question": question.question_text,
                    "answer": "The four basic data types in Python are: int for whole numbers like 42, float for decimal numbers like 3.14, str for text strings like 'Hello', and bool for boolean values True and False."
                })
            elif i == 1:
                # Question about lists
                test_answers.append({
                    "type": "AVERAGE",
                    "question": question.question_text,
                    "answer": "Lists are created using square brackets. You can use append to add items and remove to delete them."
                })
            elif i == 2:
                # Question about functions
                test_answers.append({
                    "type": "BAD",
                    "question": question.question_text,
                    "answer": "I don't know how to define functions in Python."
                })
            else:
                break
        
        print("=" * 70)
        print("SUBMITTING ANSWERS (with 12s delay for API quota)")
        print("=" * 70)
        print()
        
        total_score = 0
        max_total = 0
        
        for i, test in enumerate(test_answers):
            if i >= len(questions):
                break
                
            question = questions[i]
            print(f"Question {i+1} ({test['type']}):")
            print(f"  {question.question_text[:80]}...")
            print(f"\nStudent Answer ({test['type']}):")
            print(f"  {test['answer']}")
            print()
            
            # Validate with delay for API quota
            print("  Validating...")
            result = validator.validate_answer(
                question.question_text,
                test['answer'],
                question.ideal_answer
            )
            
            # Log the submission
            log = Log(
                student_id=student.id,
                question_id=question.id,
                answer=test['answer'],
                ai_response=result['explanation'],
                score=result['score'],
                max_score=result['max_score'],
                source_used=result['source_used'],
                confidence=result['confidence']
            )
            db.session.add(log)
            db.session.commit()
            
            total_score += result['score']
            max_total += result['max_score']
            
            print(f"  ✅ Score: {result['score']}/{result['max_score']}")
            print(f"  ✅ Correct: {result['correct']}")
            print(f"  ✅ Source: {result['source_used']}")
            print(f"  ✅ Confidence: {result['confidence']}")
            print(f"  ✅ Explanation: {result['explanation'][:150]}...")
            print()
            
            # Wait for API quota (12 seconds)
            if i < len(test_answers) - 1:
                print("  ⏳ Waiting 12 seconds for API quota...")
                time.sleep(12)
                print()
        
        print("=" * 70)
        print("SUBMISSION RESULTS")
        print("=" * 70)
        print(f"Total Score: {total_score}/{max_total} ({(total_score/max_total)*100:.1f}%)")
        print()
        
        # Analyze results
        print("Score Breakdown:")
        print(f"  Good Answer: {test_answers[0]['type']} - Expected: 8-10/10")
        print(f"  Average Answer: {test_answers[1]['type']} - Expected: 5-7/10")
        print(f"  Bad Answer: {test_answers[2]['type']} - Expected: 0-3/10")
        print()
        
        # Check if API was used
        logs = Log.query.filter_by(student_id=student.id).order_by(Log.timestamp.desc()).limit(3).all()
        api_count = sum(1 for log in logs if log.source_used == 'ai_api')
        
        print(f"API Usage: {api_count}/3 answers used Gemini API")
        print()
        
        if api_count == 3:
            print("✅ SUCCESS: All answers graded with Gemini API!")
            print("   API is working correctly with material context.")
        elif api_count > 0:
            print(f"⚠️  PARTIAL: {api_count}/3 answers used Gemini API")
            print("   Some answers may have hit quota limit.")
        else:
            print("❌ API NOT USED: All answers used fallback")
            print("   Check API key and quota.")
        
        print()
        print("=" * 70)
        print("View these submissions in the web app:")
        print("  Student: john.student@test.com")
        print("  URL: http://127.0.0.1:5002")
        print("  Go to: Student Dashboard → History")
        print("=" * 70)
        
        return True

if __name__ == '__main__':
    try:
        success = test_student_submission()
        if success:
            print("\n✅ Test completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Test failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
