from typing import List, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class SimilarityMatcher:
    """
    TF-IDF based similarity matcher for finding relevant text chunks.
    """
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.material_chunks = []
        self.tfidf_matrix = None
    
    def index_materials(self, chunks: List[str]):
        """
        Index material chunks using TF-IDF.
        """
        self.material_chunks = chunks
        if chunks:
            self.tfidf_matrix = self.vectorizer.fit_transform(chunks)
        else:
            self.tfidf_matrix = None
    
    def find_most_similar(self, query: str, top_k: int = 1) -> List[Tuple[str, float]]:
        """
        Find the most similar chunks to the query.
        Returns list of (chunk, similarity_score) tuples.
        """
        if self.tfidf_matrix is None or not self.material_chunks:
            return []
        
        query_vector = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vector, self.tfidf_matrix).flatten()
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            results.append((self.material_chunks[idx], float(similarities[idx])))
        
        return results
    
    def get_similarity_score(self, text1: str, text2: str) -> float:
        """
        Get direct similarity score between two texts.
        Uses a fresh vectorizer to avoid dimension mismatch.
        """
        fresh_vectorizer = TfidfVectorizer(stop_words='english')
        corpus = [text1, text2]
        tfidf = fresh_vectorizer.fit_transform(corpus)
        similarity = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
        return float(similarity)
