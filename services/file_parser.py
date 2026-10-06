import os
from typing import Optional

def extract_text_from_file(filepath: str, file_type: str) -> Optional[str]:
    """
    Extract text from uploaded files (PDF, DOCX, TXT).
    Returns the extracted text as a string.
    """
    try:
        if file_type == 'txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        
        elif file_type == 'pdf':
            try:
                import PyPDF2
                text = []
                with open(filepath, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text.append(page.extract_text())
                return '\n'.join(text)
            except ImportError:
                raise ImportError("PyPDF2 is required for PDF parsing. Install with: pip install PyPDF2")
        
        elif file_type == 'docx':
            try:
                import docx
                doc = docx.Document(filepath)
                text = []
                for paragraph in doc.paragraphs:
                    text.append(paragraph.text)
                return '\n'.join(text)
            except ImportError:
                raise ImportError("python-docx is required for DOCX parsing. Install with: pip install python-docx")
        
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    
    except Exception as e:
        print(f"Error extracting text from {filepath}: {e}")
        return None

def chunk_text(text: str, chunk_size: int = 500) -> list:
    """
    Split text into chunks of approximately chunk_size words.
    """
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)
    
    return chunks
