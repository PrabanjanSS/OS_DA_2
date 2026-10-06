# AI Grading System

An intelligent automated grading platform using RAG (Retrieval-Augmented Generation), AI validation, and OS concurrency concepts (threading, locks, mutual exclusion).

## Features

- **Authentication**: Secure login/signup with role-based access (Teacher/Student)
- **Teacher Module**:
  - Create question sets
  - Upload study materials (PDF, DOCX, TXT)
  - Grant access to students with attempt limits
  - View detailed analytics and submission logs
- **Student Module**:
  - View assigned question sets
  - Submit answers with AI validation
  - Get instant feedback and scores
  - Track submission history
- **AI Validation Chain**:
  - Priority 1: RAG-based validation using teacher materials (TF-IDF + cosine similarity)
  - Priority 2: Google Gemini API for intelligent grading (FREE)
  - Priority 3: Fallback to local similarity matching
- **OS Concepts**:
  - Thread pool for concurrent validation tasks
  - Locks for mutual exclusion (prevents race conditions)
  - Critical sections for shared resource access

## Tech Stack

- **Backend**: Python Flask
- **Database**: SQLite (built-in, no installation needed)
- **Authentication**: Flask-Login + bcrypt password hashing
- **AI/ML**: 
  - Anthropic Claude API
  - scikit-learn (TF-IDF, cosine similarity)
- **File Processing**: PyPDF2, python-docx
- **Frontend**: HTML + Tailwind CSS (via CDN) - vibrant, custom design

## Prerequisites

1. **Python 3.10+** - Download from [python.org](https://python.org/downloads/)
   - During installation, check "Add to PATH"

2. **No other installations needed!**
   - SQLite is built into Python
   - No Node.js required
   - No PostgreSQL required
   - No vector DB server required

## Installation

1. Clone or navigate to the project directory:
```bash
cd /Users/ssprabanjan1/OS_DA2
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
```

4. Edit `.env` file and add your Google Gemini API key:
```bash
# Get your key from: https://makersuite.google.com/app/apikey
GEMINI_API_KEY=your-actual-api-key-here
```

5. Run the application:
```bash
python app.py
```

The application will start on `http://127.0.0.1:5000`

## Usage

### For Teachers

1. Sign up as a **Teacher**
2. Create a new **Question Set**
3. Upload **Materials** (PDF/DOCX/TXT) - these will be used for RAG-based validation
4. Add **Questions** to the set (optional: add ideal answers for reference)
5. **Grant Access** to students by entering their email and max attempts
6. View **Analytics** to see student performance and validation sources

### For Students

1. Sign up as a **Student**
2. Wait for teacher to grant access to question sets
3. View **Dashboard** to see assigned sets
4. **Start Attempt** - answer questions within attempt limit
5. View **Results** with scores, feedback, and validation source used
6. Check **History** for all past submissions

## Project Structure

```
OS_DA2/
├── app.py                 # Flask application entry point
├── config.py              # Configuration and environment variables
├── models.py              # Database models (User, Set, Material, Question, etc.)
├── extensions.py          # Flask extensions (db, login_manager)
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── auth/
│   ├── __init__.py
│   └── routes.py          # Authentication routes (signup, login, logout)
├── teacher/
│   ├── __init__.py
│   └── routes.py          # Teacher routes (create set, upload, grant access)
├── student/
│   ├── __init__.py
│   └── routes.py          # Student routes (view sets, submit answers)
├── services/
│   ├── __init__.py
│   ├── file_parser.py     # PDF/DOCX/TXT text extraction
│   ├── similarity.py      # TF-IDF + cosine similarity
│   ├── concurrency.py     # Thread pool & locks (OS concepts)
│   └── validator.py       # Validation chain (RAG → AI → Fallback)
├── templates/
│   ├── base.html          # Base template with Tailwind CSS
│   ├── index.html         # Landing page
│   ├── auth/
│   │   ├── login.html
│   │   └── signup.html
│   ├── teacher/
│   │   ├── dashboard.html
│   │   ├── create_set.html
│   │   ├── view_set.html
│   │   └── analytics.html
│   └── student/
│       ├── dashboard.html
│       ├── view_set.html
│       ├── results.html
│       └── history.html
└── static/
    └── uploads/           # Uploaded materials storage
```

## OS Concepts Demonstrated

### 1. Threading
- **Thread Pool**: `ThreadPoolExecutor` with 4 workers for concurrent validation
- Purpose: Handle multiple AI API calls simultaneously without blocking the main thread

### 2. Mutual Exclusion (Locks)
- **attempt_lock**: Prevents race conditions when incrementing attempt counters
- **log_lock**: Ensures thread-safe database logging
- Purpose: Critical sections protect shared resources from concurrent modification

### 3. Critical Sections
- Functions wrapped with `with lock:` ensure only one thread executes at a time
- Prevents data corruption from simultaneous writes

### 4. Synchronization
- Thread-safe counter for student attempts
- Thread-safe logging of submissions
- Demonstrates producer-consumer pattern with thread pool

## Validation Chain

The system uses a priority-based fallback system:

1. **Material Match (RAG)**: If teacher materials exist and similarity > threshold
   - Uses TF-IDF to find relevant text chunks
   - Validates answer against teacher's own materials
   - Source logged as `material_match`

2. **AI API**: If no materials or low similarity
   - Sends question + answer to Anthropic Claude
   - Returns structured JSON with score and explanation
   - Source logged as `ai_api`

3. **Fallback Dataset**: If AI API fails
   - Uses local TF-IDF similarity against ideal answer
   - No external API call needed
   - Source logged as `fallback_dataset`

## API Keys

### Getting Google Gemini API Key (FREE)

1. Go to [https://makersuite.google.com/app/apikey](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key and add it to your `.env` file

Gemini API is free to use with generous limits for development and testing.

## Troubleshooting

### Import Errors
If you get import errors, make sure you installed all dependencies:
```bash
pip install -r requirements.txt
```

### Database Issues
If you encounter database errors, delete the existing database and restart:
```bash
rm grading_system.db
python app.py
```

### API Key Issues
If validation always uses fallback mode, check:
1. Your `.env` file exists
2. `GEMINI_API_KEY` is set correctly
3. Your Google account has access to Gemini API

### File Upload Issues
If file uploads fail:
1. Check file format (PDF, DOCX, TXT only)
2. Ensure file size < 16MB
3. Check that `static/uploads/` directory exists

## Security Notes

- Passwords are hashed using bcrypt (never stored in plain text)
- Session-based authentication with Flask-Login
- Role-based access control (teachers vs students)
- Input validation on all forms
- File type restrictions for uploads

## Demo for Viva

Key points to highlight during your OS viva:

1. **Threading**: Explain how the thread pool handles concurrent validation requests
2. **Mutual Exclusion**: Show how locks prevent race conditions on attempt counters
3. **Critical Sections**: Demonstrate the `with lock:` pattern in `concurrency.py`
4. **Synchronization**: Explain how thread-safe logging prevents data corruption
5. **Producer-Consumer**: The thread pool acts as consumers for validation tasks

## License

This is a course project for educational purposes.
