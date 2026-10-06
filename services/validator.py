import json
import google.generativeai as genai
import time
from typing import Dict, List, Optional
from config import Config
from services.similarity import SimilarityMatcher
from services.concurrency import run_in_thread

class AnswerValidator:
    """
    Validation chain: Materials → AI API → Fallback Dataset
    Demonstrates priority-based fallback system.
    """
    
    def __init__(self):
        self.similarity_matcher = SimilarityMatcher()
        self.client = None
        self.last_api_call = 0
        self.api_call_delay = 12  # 12 seconds between API calls to avoid quota (5 per minute limit)
        
        if Config.GEMINI_API_KEY:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            # Use gemini-2.5-flash which has better free tier availability
            self.client = genai.GenerativeModel('models/gemini-2.5-flash')
    
    def index_set_materials(self, materials: List[str]):
        """
        Index materials for this set using TF-IDF.
        """
        chunks = []
        for material_text in materials:
            if material_text:
                from services.file_parser import chunk_text
                chunks.extend(chunk_text(material_text, chunk_size=500))
        
        if chunks:
            self.similarity_matcher.index_materials(chunks)
    
    def validate_answer(self, question: str, answer: str, ideal_answer: Optional[str] = None) -> Dict:
        """
        Main validation chain with priority fallback.
        Returns: {
            'score': float,
            'max_score': int,
            'correct': bool,
            'explanation': str,
            'confidence': float,
            'source_used': str
        }
        """
        # Priority 1: Use AI API with teacher materials as context (RAG-style)
        if self.client:
            # Rate limiting: wait between API calls
            current_time = time.time()
            if current_time - self.last_api_call < self.api_call_delay:
                time.sleep(self.api_call_delay - (current_time - self.last_api_call))
            
            # Get relevant chunks from materials to provide as context
            relevant_chunks = self.similarity_matcher.find_most_similar(question, top_k=3)
            context = '\n'.join([chunk[0] for chunk in relevant_chunks]) if relevant_chunks else ""
            
            try:
                result = self._validate_with_ai(question, answer, ideal_answer, context)
                self.last_api_call = time.time()
                return result
            except Exception as e:
                print(f"AI API failed: {e}, falling back to local dataset")
        
        # Priority 2: Use teacher materials with local similarity (RAG-style)
        relevant_chunks = self.similarity_matcher.find_most_similar(question, top_k=2)
        
        if relevant_chunks and relevant_chunks[0][1] > Config.SIMILARITY_THRESHOLD:
            context = '\n'.join([chunk[0] for chunk in relevant_chunks])
            return self._validate_with_materials(question, answer, context, relevant_chunks[0][1])
        
        # Priority 3: Fallback to local similarity (no external API)
        return self._validate_with_similarity(question, answer, ideal_answer)
    
    def _validate_with_materials(self, question: str, answer: str, context: str, similarity: float) -> Dict:
        """
        Validate using teacher materials as reference.
        Improved scoring to be more lenient.
        """
        similarity_score = self.similarity_matcher.get_similarity_score(answer, context)
        
        # More lenient scoring: boost similarity score
        # If similarity is > 0.1, give it more weight
        if similarity_score > 0.1:
            boosted_score = min(similarity_score * 1.5, 1.0)  # Boost by 50%, max 1.0
        else:
            boosted_score = similarity_score
        
        # Scale to score (0-10)
        score = round(boosted_score * Config.MAX_SCORE, 2)
        
        # Minimum score of 1 if there's any similarity at all
        if similarity_score > 0 and score < 1:
            score = 1.0
        
        return {
            'score': score,
            'max_score': Config.MAX_SCORE,
            'correct': score >= Config.MAX_SCORE * 0.5,  # Lowered threshold from 0.6 to 0.5
            'explanation': f"Answer validated against teacher materials. Similarity: {similarity_score:.2f} (boosted: {boosted_score:.2f})",
            'confidence': similarity_score,
            'source_used': 'material_match'
        }
    
    def _validate_with_ai(self, question: str, answer: str, ideal_answer: Optional[str] = None, context: str = "") -> Dict:
        """
        Validate using Google Gemini API with teacher materials as context.
        """
        prompt = f"""You are an answer grading assistant. Grade the student's answer based on the question and the provided reference materials.

Question: {question}

Student Answer: {answer}
"""
        
        if context:
            prompt += f"""
Reference Materials (from teacher's uploaded content):
{context}

IMPORTANT: Use these reference materials to determine if the student's answer is correct. The student should demonstrate understanding of the concepts covered in these materials.
"""
        
        if ideal_answer:
            prompt += f"\nIdeal Answer (reference): {ideal_answer}"
        
        prompt += """
Grade the answer on a scale of 0-10 based on:
1. Accuracy and completeness
2. Understanding of key concepts
3. Use of correct terminology
4. Relevance to the question

Respond ONLY with a JSON object in this exact format:
{
    "score": <number 0-10>,
    "correct": <boolean>,
    "explanation": "<brief explanation of why the answer received this score>",
    "confidence": <number 0-1>
}
"""
        
        try:
            response = self.client.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=1024,  # Increased to 1024 to get full JSON
                )
            )
            
            response_text = response.text
            print(f"Raw AI response length: {len(response_text)} characters")  # Debug logging
            
            # Try to extract JSON from response (might be in markdown code blocks)
            json_text = response_text
            if '```json' in response_text:
                # Extract JSON from markdown code block
                start = response_text.find('```json') + 7
                end = response_text.find('```', start)
                if end > start:
                    json_text = response_text[start:end].strip()
            elif '```' in response_text:
                # Extract from any code block
                start = response_text.find('```') + 3
                end = response_text.find('```', start)
                if end > start:
                    json_text = response_text[start:end].strip()
            
            # Try to parse JSON
            try:
                result = json.loads(json_text)
            except json.JSONDecodeError:
                # If JSON is incomplete, try to fix it by closing braces
                # Count opening and closing braces
                open_braces = json_text.count('{')
                close_braces = json_text.count('}')
                if open_braces > close_braces:
                    json_text += '}' * (open_braces - close_braces)
                
                # Count opening and closing brackets
                open_brackets = json_text.count('[')
                close_brackets = json_text.count(']')
                if open_brackets > close_brackets:
                    json_text += ']' * (open_brackets - close_brackets)
                
                # Try parsing again
                result = json.loads(json_text)
            
            return {
                'score': result.get('score', 0),
                'max_score': Config.MAX_SCORE,
                'correct': result.get('correct', False),
                'explanation': result.get('explanation', ''),
                'confidence': result.get('confidence', 0.5),
                'source_used': 'ai_api'
            }
        except Exception as e:
            print(f"Error parsing AI response: {e}")
            print(f"Response was: {response_text if 'response_text' in locals() else 'N/A'}")
            raise
    
    def _validate_with_similarity(self, question: str, answer: str, ideal_answer: Optional[str] = None) -> Dict:
        """
        Fallback: Use local TF-IDF similarity without external API.
        Improved scoring to be more lenient.
        """
        if ideal_answer:
            similarity = self.similarity_matcher.get_similarity_score(answer, ideal_answer)
            # Boost similarity for better scoring
            boosted_similarity = min(similarity * 1.3, 1.0)  # Boost by 30%
            score = round(boosted_similarity * Config.MAX_SCORE, 2)
        else:
            # If no ideal answer, check against question keywords
            similarity = self.similarity_matcher.get_similarity_score(answer, question)
            boosted_similarity = min(similarity * 1.5, 1.0)  # Boost by 50%
            score = round(boosted_similarity * Config.MAX_SCORE * 0.7, 2)  # Increased from 0.5 to 0.7
        
        # Minimum score of 1 if there's any similarity
        if similarity > 0 and score < 1:
            score = 1.0
        
        return {
            'score': score,
            'max_score': Config.MAX_SCORE,
            'correct': score >= Config.MAX_SCORE * 0.5,  # Lowered from 0.6 to 0.5
            'explanation': f'Validated using local similarity matching (fallback mode). Similarity: {similarity:.2f}',
            'confidence': boosted_similarity,
            'source_used': 'fallback_dataset'
        }
