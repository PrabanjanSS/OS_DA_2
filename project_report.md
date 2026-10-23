# OS_DA2: Automated AI Grading & Assessment System
## Comprehensive Project Engineering Report

### 1. Executive Summary
OS_DA2 is a state-of-the-art, AI-driven assessment platform designed to automate the lifecycle of student evaluations. From generating unique question pools to grading complex file-based assignments, the system leverages Google's Gemini AI to provide high-fidelity feedback and objective scoring. It is built with a focus on academic integrity, scalability, and an editorial design aesthetic.

---

### 2. Core Architecture & Tech Stack
- **Framework**: Python 3.12 / Flask (WSGI-compliant).
- **Database**: SQLite 3 with SQLAlchemy ORM. The schema uses foreign key constraints and unique indexes to ensure data integrity.
- **AI Engine**: Google Gemini API (`models/gemini-2.5-flash` with `flash-lite` fallback).
- **Design System**: Custom CSS built on a 4px grid system with strict token-based separation of concerns.
- **Reporting**: `python-docx` for Word generation and `openpyxl` for Excel analytics.
- **Text Extraction**: `PyPDF2` and `python-docx` for processing student uploads and teacher materials.

---

### 3. User Roles & Authentication
The system implements a role-based access control (RBAC) system:
- **Teachers**:
    - Registration is gated by a `TEACHER_SIGNUP_CODE` defined in the environment.
    - Full control over question sets, class groups, and manual grade overrides.
    - Dashboard access for class-wide analytics and report generation.
- **Students**:
    - Self-registration allowed.
    - Access to assigned question sets based on email or class group membership.
    - Attempt history and AI-generated feedback review.
- **Auth Features**:
    - `PBKDF2` password hashing via `werkzeug.security`.
    - Session-based persistence with role-aware redirection.
    - `SESSION_TIMEOUT_MINUTES` configuration for idle logout security.

---

### 4. Question Set Management
A "Set" is the primary unit of assessment. Features include:
- **Delivery Modes**:
    - **Timed Quiz**: Students type answers directly into the portal. Supports an active attempt clock.
    - **Assignment**: Students upload a single Word/PDF answer sheet. The system automatically segments it for grading.
- **Material Access Control**:
    - **Open Book**: Materials are visible in a sidebar during the attempt.
    - **Closed Book**: Materials are withdrawn once the "Start Attempt" button is clicked.
- **Submission Windows**:
    - **Soft Deadline (`due_at`)**: Flags submissions as late but allows them to arrive.
    - **Hard Deadline (`submissions_close_at`)**: Blocks the submission link entirely.
- **Attempt Limits**: Configurable max attempts per student/set.

---

### 5. AI Question Pool Generation
To prevent collusion, the system can generate a randomized pool of questions:
- **Parameters**: Topic, pool size, questions-per-student, difficulty (1–5), and question "kind" (e.g., Numerical, Short Answer, One Word).
- **Random Allocation**: Uses a `least-used → random` strategy to ensure an even distribution of questions across the class.
- **Integrity**: Each student receives a unique, shuffled subset of the pool, recorded in the `QuestionAllocation` table to prevent reshuffling on page reloads.

---

### 6. Intelligent Grading Chain
The `AnswerValidator` implements a three-tier priority fallback system:
1. **Tier 1: Gemini AI RAG**: The student's answer is graded by Gemini, using relevant teacher-provided materials (retrieved via TF-IDF) as grounding context.
2. **Tier 2: Local RAG**: If the AI API fails, the system uses TF-IDF similarity to compare the student's answer directly against relevant chunks of the teacher's materials.
3. **Tier 3: Keyword Similarity**: A final fallback that compares the student's answer to the teacher's ideal answer or the question text itself.
- **Strictness Levels (1–5)**:
    - **1 (Very Lenient)**: Threshold 0.35. Awards credit for rough understanding.
    - **3 (Balanced)**: Threshold 0.50. Standard academic rigor.
    - **5 (Very Strict)**: Threshold 0.70. Requires precise terminology and completeness.

---

### 7. Assignment Processing (The Splitter)
For file-based assignments, the `services/splitter.py` module handles document segmentation:
- **AI-Based Splitting**: Uses Gemini to identify where one answer ends and the next begins based on question text.
- **Marker-Based Heuristic**: Fallback that detects common student markers (e.g., "Q1", "Ans 3.", "Question 4") using regular expressions.
- **Paragraph Heuristic**: Last resort that treats each blank-line-separated block as a separate answer.
- **Review Flow**: Teachers can review the "Split Note" to see how the system partitioned the document before approving the AI scores.

---

### 8. Reporting & Analytics
- **Word Paper Generation**: Automatically renders the current question pool into a professionally formatted `.docx` file for students to download.
- **Detailed Answer Report (Excel)**: A per-answer breakdown including student response, AI reasoning, key points, and the specific validation source used (AI vs. Local).
- **Class Marksheet (Excel)**: A matrix view of a class's performance across multiple assignments, including total marks and percentages.
- **Teacher Analytics**: Dashboard view of source usage (how often AI is used vs. materials) and student performance trends.

---

### 9. Engineering Highlights & Concurrency
- **Allocation Lock**: Uses a threading lock to prevent race conditions when multiple students start a pool-based quiz simultaneously.
- **API Rate Limiting**: Implements a 12-second delay between Gemini calls to stay within the 5-requests-per-minute Free Tier quota.
- **JSON Resilience**: The AI parser uses innermost-brace extraction and automated bracket repair to handle truncated or malformed AI responses.
- **Data Isolation**: SQLite currently runs in single-thread mode for stability, with a future-ready schema for WAL mode.

---

### 10. Design System (Visual Identity)
- **Aesthetic**: Clean, editorial, "paper-like" layout inspired by Notion and Linear.
- **Typography**: `Instrument Serif` for headings (regular weight), `Geist Sans` for UI and body text.
- **Type Scale**: Specific px constraints (12, 13, 14, 16, 20, 28, 40) for hierarchy.
- **Layout Tokens**: 4px base scale for spacing, 6px radius for controls, 10px for cards.
- **Visual Guards**: Explicitly avoids emojis, gradients, and glow shadows to maintain a high-information-density professional look.
