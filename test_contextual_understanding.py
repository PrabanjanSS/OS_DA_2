"""
Test if AI truly understands contextual meaning vs simple text matching
This tests whether the AI can recognize correct answers that use different wording
"""
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from models import db, Set, Material
from services.validator import AnswerValidator
from services.file_parser import chunk_text

def test_contextual_understanding():
    """Test AI's ability to understand context vs simple matching"""
    
    app = create_app()
    
    with app.app_context():
        print("=" * 70)
        print("TEST: AI CONTEXTUAL UNDERSTANDING VS TEXT MATCHING")
        print("=" * 70)
        print()
        
        # Create a sample material
        material_content = """
Computer Science Fundamentals

A variable is a named storage location in computer memory that holds a value.
Variables are used to store data that can be referenced and manipulated in a program.

Loops are programming constructs that allow repeated execution of a block of code.
They help automate repetitive tasks and make code more efficient.

Functions are reusable blocks of code that perform specific tasks.
They take input (parameters) and return output (return values).
"""
        
        # Create a temporary material in database
        question_set = Set.query.filter_by(title="Context Understanding Test").first()
        if not question_set:
            question_set = Set(
                teacher_id=1,
                title="Context Understanding Test",
                description="Test AI's contextual understanding"
            )
            db.session.add(question_set)
            db.session.commit()
            
            material = Material(
                set_id=question_set.id,
                filename="test_material.txt",
                filepath="/tmp/test_material.txt",
                file_type="txt",
                processed_text=material_content
            )
            db.session.add(material)
            db.session.commit()
        
        print(f"✓ Created/Found test question set")
        print()
        
        # Initialize validator
        validator = AnswerValidator()
        validator.index_set_materials([material_content])
        print("✓ Validator initialized with material")
        print()
        
        # Test cases that require contextual understanding
        test_cases = [
            {
                "name": "TEST 1: Different Wording, Same Meaning",
                "question": "What is a variable in programming?",
                "material_text": "A variable is a named storage location in computer memory that holds a value.",
                "answer": "A variable is a container in memory that stores data for a program to use.",
                "expected": "Should recognize this as correct despite different wording",
                "semantic_match": True
            },
            {
                "name": "TEST 2: Synonyms and Rephrasing",
                "question": "What do loops do in programming?",
                "material_text": "Loops are programming constructs that allow repeated execution of a block of code.",
                "answer": "Loops enable running the same code multiple times automatically.",
                "expected": "Should recognize 'repeated execution' = 'running multiple times'",
                "semantic_match": True
            },
            {
                "name": "TEST 3: Simplified Explanation",
                "question": "What are functions?",
                "material_text": "Functions are reusable blocks of code that perform specific tasks.",
                "answer": "Functions are code segments you can reuse to do specific jobs.",
                "expected": "Should recognize 'reusable blocks' = 'code segments you can reuse'",
                "semantic_match": True
            },
            {
                "name": "TEST 4: Wrong Concept (Should Fail)",
                "question": "What is a variable?",
                "material_text": "A variable is a named storage location in computer memory that holds a value.",
                "answer": "A variable is a type of loop that iterates over data.",
                "expected": "Should reject this - wrong concept entirely",
                "semantic_match": False
            },
            {
                "name": "TEST 5: Partially Correct but Incomplete",
                "question": "What do loops do?",
                "material_text": "Loops are programming constructs that allow repeated execution of a block of code.",
                "answer": "Loops run code.",
                "expected": "Should give partial credit - correct but incomplete",
                "semantic_match": True
            }
        ]
        
        print("=" * 70)
        print("TESTING CONTEXTUAL UNDERSTANDING")
        print("=" * 70)
        print()
        
        results = []
        
        for i, test in enumerate(test_cases):
            print(f"{test['name']}")
            print(f"Question: {test['question']}")
            print(f"Material says: {test['material_text']}")
            print(f"Student answered: {test['answer']}")
            print(f"Expected: {test['expected']}")
            print()
            
            # Validate with AI
            print("Validating with AI...")
            result = validator.validate_answer(
                test['question'],
                test['answer'],
                test['material_text']  # Use material text as ideal answer
            )
            
            results.append({
                'test': test,
                'result': result
            })
            
            print(f"  Score: {result['score']}/{result['max_score']}")
            print(f"  Source: {result['source_used']}")
            print(f"  Explanation: {result['explanation'][:200]}...")
            print()
            
            # Wait for API quota
            if i < len(test_cases) - 1:
                print("  ⏳ Waiting 12 seconds for API quota...")
                time.sleep(12)
                print()
        
        print("=" * 70)
        print("CONTEXTUAL UNDERSTANDING ANALYSIS")
        print("=" * 70)
        print()
        
        semantic_correct = 0
        semantic_incorrect = 0
        
        for i, data in enumerate(results):
            test = data['test']
            result = data['result']
            
            print(f"{test['name']}:")
            print(f"  Semantic Match Expected: {test['semantic_match']}")
            print(f"  AI Score: {result['score']}/{result['max_score']}")
            print(f"  AI Correct: {result['correct']}")
            
            if test['semantic_match']:
                if result['score'] >= 5:
                    print(f"  ✅ PASS: AI recognized semantic meaning")
                    semantic_correct += 1
                else:
                    print(f"  ❌ FAIL: AI didn't recognize semantic meaning")
                    semantic_incorrect += 1
            else:
                if result['score'] < 5:
                    print(f"  ✅ PASS: AI correctly rejected wrong answer")
                    semantic_correct += 1
                else:
                    print(f"  ❌ FAIL: AI incorrectly accepted wrong answer")
                    semantic_incorrect += 1
            print()
        
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Total Tests: {len(results)}")
        print(f"Semantic Understanding Passed: {semantic_correct}")
        print(f"Semantic Understanding Failed: {semantic_incorrect}")
        print()
        
        if semantic_correct >= 4:
            print("✅ SUCCESS: AI demonstrates strong contextual understanding!")
            print("   The AI can recognize correct answers even with different wording.")
        elif semantic_correct >= 3:
            print("⚠️  PARTIAL: AI shows some contextual understanding")
            print("   But struggles with some cases.")
        else:
            print("❌ FAIL: AI lacks contextual understanding")
            print("   It may be doing simple text matching only.")
        
        print("=" * 70)
        
        return semantic_correct >= 3

if __name__ == '__main__':
    try:
        success = test_contextual_understanding()
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
