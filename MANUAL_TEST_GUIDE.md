# Manual Testing Guide - AI Grading System

## Prerequisites
- Application running on: http://127.0.0.1:5001
- Gemini API key configured in `.env` file

---

## TEST 1: Teacher - Create Account and Login

### Step 1: Sign Up as Teacher
1. Go to http://127.0.0.1:5001
2. Click "Sign Up as Teacher"
3. Fill in:
   - **Name:** John Teacher
   - **Email:** john.teacher@test.com
   - **Password:** teacher123
   - **Role:** Teacher
4. Click "Create Account"
5. You should be redirected to login page

### Step 2: Login as Teacher
1. Enter email: `john.teacher@test.com`
2. Enter password: `teacher123`
3. Click "Login"
4. You should see "Teacher Dashboard"

---

## TEST 2: Teacher - Create Question Set

### Step 1: Create New Set
1. On Teacher Dashboard, click "+ Create New Set"
2. Fill in:
   - **Set Title:** Python Basics Quiz
   - **Description:** Test your knowledge of Python fundamentals
3. Click "Create Set"
4. You should see the set view page

---

## TEST 3: Teacher - Upload Study Material

### Step 1: Create a Sample Material File
Create a file named `python_notes.txt` with this content:

```
Python Programming Fundamentals

Python is a high-level, interpreted programming language created by Guido van Rossum. 
It emphasizes code readability with its notable use of significant whitespace.

KEY CONCEPTS:

1. Variables and Data Types:
   - int: Whole numbers (e.g., 42, -7)
   - float: Decimal numbers (e.g., 3.14, -0.5)
   - str: Text strings (e.g., "Hello World")
   - bool: Boolean values (True, False)
   
   Example:
   age = 25
   price = 19.99
   name = "Alice"
   is_student = True

2. Lists:
   Lists are ordered, mutable collections that can hold multiple items.
   Created using square brackets [].
   
   Example:
   fruits = ["apple", "banana", "cherry"]
   numbers = [1, 2, 3, 4, 5]
   
   List operations:
   - append(): Add item to end
   - remove(): Remove specific item
   - len(): Get length

3. Functions:
   Functions are reusable blocks of code defined using the 'def' keyword.
   They can take parameters and return values.
   
   Example:
   def greet(name):
       return f"Hello, {name}!"
   
   def calculate_area(length, width):
       return length * width

4. Conditionals:
   Python uses if, elif, and else for conditional execution.
   
   Example:
   if age >= 18:
       print("Adult")
   elif age >= 13:
       print("Teenager")
   else:
       print("Child")
```

### Step 2: Upload the Material
1. On the set view page, find "📚 Upload Materials" section
2. Click "Choose File" and select `python_notes.txt`
3. Click "Upload Material"
4. You should see the file listed under uploaded materials

---

## TEST 4: Teacher - Add Questions

### Question 1:
- **Question Text:** What are the four basic data types in Python and give an example of each?
- **Ideal Answer:** The four basic data types are: int (whole numbers like 42), float (decimals like 3.14), str (text like "Hello"), and bool (True/False)
- **Max Score:** 10
- Click "Add Question"

### Question 2:
- **Question Text:** How do you create a list in Python and what are two common list operations?
- **Ideal Answer:** Lists are created using square brackets. Common operations include append() to add items and remove() to delete items.
- **Max Score:** 10
- Click "Add Question"

### Question 3:
- **Question Text:** How do you define a function in Python? Provide an example.
- **Ideal Answer:** Functions are defined using the 'def' keyword followed by the function name and parameters. Example: def greet(name): return f"Hello, {name}!"
- **Max Score:** 10
- Click "Add Question"

---

## TEST 5: Teacher - Grant Student Access

### Step 1: Create Student Account
1. Open a new browser window or logout
2. Go to http://127.0.0.1:5001
3. Click "Sign Up as Student"
4. Fill in:
   - **Name:** Jane Student
   - **Email:** jane.student@test.com
   - **Password:** student123
   - **Role:** Student
5. Click "Create Account"

### Step 2: Login as Teacher (back to first window)
1. If logged out, login as: `john.teacher@test.com` / `teacher123`
2. Go to your "Python Basics Quiz" set
3. Find "🔑 Grant Student Access" section
4. Enter student email: `jane.student@test.com`
5. Set Max Attempts: `2`
6. Click "Grant Access"
7. You should see the student listed with 0/2 attempts used

---

## TEST 6: Student - View and Attempt Quiz

### Step 1: Login as Student
1. Go to http://127.0.0.1:5001
2. Login with: `jane.student@test.com` / `student123`
3. You should see "Student Dashboard"
4. You should see "Python Basics Quiz" with 2 attempts remaining

### Step 2: Start Attempt
1. Click "Start Attempt" on the quiz
2. You should see 3 questions

### Step 3: Answer Questions

**Question 1 - What are the four basic data types?**
- **Sample Good Answer:** The four basic data types in Python are int for whole numbers like 42, float for decimal numbers like 3.14, str for text strings like "Hello", and bool for boolean values True and False.

**Question 2 - How do you create a list?**
- **Sample Good Answer:** Lists in Python are created using square brackets. For example: fruits = ["apple", "banana"]. Two common operations are append() to add items and remove() to delete items.

**Question 3 - How do you define a function?**
- **Sample Good Answer:** Functions are defined using the def keyword. For example: def my_function(param): return param * 2. This creates a reusable block of code.

### Step 4: Submit Answers
1. Click "Submit Answers"
2. Wait for grading (should take 2-5 seconds)
3. You should see your results page with scores and explanations

---

## TEST 7: Student - View Results

### What to Check:
- ✅ Each question shows a score (0-10)
- ✅ You see total score and percentage
- ✅ Each answer has an explanation
- ✅ Validation source is shown (ai_api or material_match)
- ✅ Attempts remaining decreased (now 1/2)

---

## TEST 8: Student - View History

### Step 1: Go to History
1. On Student Dashboard, click "View History →"
2. You should see all your submissions
3. Each entry shows:
   - Question text
   - Your answer
   - Score
   - Validation source
   - Timestamp

---

## TEST 9: Teacher - View Analytics

### Step 1: Login as Teacher
1. Login as: `john.teacher@test.com` / `teacher123`
2. Go to "Python Basics Quiz" set
3. Click "View Analytics →"

### What to Check:
- ✅ Total submissions count
- ✅ Average score
- ✅ Validation source breakdown (ai_api vs material_match)
- ✅ Detailed submission table with:
  - Student name
  - Question
  - Score
  - Source used
  - Confidence
  - Timestamp

---

## TEST 10: Test Attempt Limits

### Step 1: Student Second Attempt
1. Login as student: `jane.student@test.com` / `student123`
2. Go to Student Dashboard
3. Start another attempt on "Python Basics Quiz"
4. Submit answers (can use same or different answers)
5. Check that attempts now show 0/2 remaining

### Step 2: Try Third Attempt (Should Fail)
1. Try to start another attempt
2. You should see "No Attempts Left" button (disabled)
3. Or you should be blocked from starting

---

## TEST 11: Test AI Grading with Material Context

### Good Answer Test:
- Submit an answer that closely matches the uploaded material
- Expected: High score (8-10/10)
- Expected: Source should be `ai_api` (if quota available)
- Expected: Explanation should reference material content

### Poor Answer Test:
- Submit an incorrect or irrelevant answer
- Expected: Low score (0-3/10)
- Expected: Explanation should explain why it's wrong

### Example Test Answers:

**Test Good Answer:**
```
Python has four basic data types: int for integers like 42, 
float for decimals like 3.14, str for strings like "text", 
and bool for True/False values.
```

**Test Poor Answer:**
```
I don't know the data types in Python.
```

---

## TEST 12: Test Fallback System

### If API Quota Exceeded:
1. The system should automatically use `material_match` as source
2. Grading should still work using TF-IDF similarity
3. Students can still submit answers
4. No errors should be shown to the user

---

## SAMPLE TEST DATA SUMMARY

### Teacher Account:
- **Email:** john.teacher@test.com
- **Password:** teacher123
- **Set Name:** Python Basics Quiz
- **Material:** python_notes.txt (use content from TEST 3)
- **Questions:** 3 questions (use content from TEST 4)

### Student Account:
- **Email:** jane.student@test.com
- **Password:** student123
- **Max Attempts:** 2

### Good Answer Samples:
- Data types: int, float, str, bool with examples
- Lists: Created with [], operations: append(), remove()
- Functions: def keyword, parameters, return statement

### Poor Answer Samples:
- "I don't know"
- Wrong information
- Irrelevant content

---

## EXPECTED RESULTS

### Successful Grading with AI:
- Source: `ai_api`
- Score: 8-10/10 for good answers
- Score: 0-3/10 for poor answers
- Explanation: Detailed and context-aware

### Fallback Grading (No API):
- Source: `material_match` or `fallback_dataset`
- Score: Based on TF-IDF similarity
- Explanation: Based on similarity matching

---

## TROUBLESHOOTING

### If AI Not Working:
- Check if Gemini API quota exceeded (wait ~48 seconds)
- Check `.env` file has valid GEMINI_API_KEY
- System will automatically fallback to local matching

### If File Upload Fails:
- Ensure file is .txt, .pdf, or .docx
- Ensure file size < 16MB
- Check `static/uploads/` directory exists

### If Access Grant Fails:
- Ensure student email is correct
- Ensure student account exists with role="student"
- Check for typos in email address

---

## VERIFICATION CHECKLIST

- [ ] Teacher can sign up and login
- [ ] Teacher can create question set
- [ ] Teacher can upload material
- [ ] Teacher can add questions
- [ ] Teacher can grant student access
- [ ] Student can login and see assigned sets
- [ ] Student can attempt quiz
- [ ] Student can submit answers
- [ ] Grading works (AI or fallback)
- [ ] Student can view results
- [ ] Student can view history
- [ ] Teacher can view analytics
- [ ] Attempt limits work correctly
- [ ] Fallback system works when API unavailable

---

## QUICK TEST CREDENTIALS

### Teacher:
- Email: `teacher_test@example.com`
- Password: `teacher123`

### Student:
- Email: `student_test@example.com`
- Password: `student123`

(These were created by the automated test script)
