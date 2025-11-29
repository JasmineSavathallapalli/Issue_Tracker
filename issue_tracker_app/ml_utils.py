"""
NLP-based automatic issue categorization
Uses keyword matching and can be upgraded to ML models
"""

import re
from typing import Dict, Tuple, List

class IssueClassifier:
    """
    Classifies issues into categories using NLP techniques
    """
    
    # Keyword patterns for each category
    CATEGORY_KEYWORDS = {
        'bug': [
            'bug', 'error', 'crash', 'broken', 'not working', 'fails', 'failure',
            'issue', 'problem', 'wrong', 'incorrect', 'unexpected', 'exception',
            'traceback', 'stack trace', 'null pointer', '500 error', '404', 
            'syntax error', 'runtime error', 'does not work', "doesn't work",
            'fix', 'broke', 'regression', 'defect', 'fault'
        ],
        'feature': [
            'feature', 'add', 'new', 'request', 'could', 'should', 'would like',
            'enhancement', 'improve', 'suggestion', 'propose', 'ability to',
            'it would be nice', 'please add', 'can we have', 'is it possible',
            'implement', 'create', 'build', 'develop', 'want', 'need'
        ],
        'question': [
            'question', 'how', 'what', 'why', 'when', 'where', 'who', 'which',
            'can i', 'is it', 'does', 'help', 'guide', 'documentation', 
            'explain', 'clarify', 'understand', '?', 'wondering', 'confused',
            'not sure', 'how to', 'way to'
        ],
        'enhancement': [
            'enhance', 'better', 'optimize', 'performance', 'speed up', 
            'refactor', 'redesign', 'upgrade', 'modernize', 'efficiency',
            'scalability', 'usability', 'user experience', 'ux', 'ui',
            'polish', 'cleanup', 'streamline', 'faster'
        ],
        'documentation': [
            'documentation', 'docs', 'readme', 'guide', 'tutorial', 'example',
            'wiki', 'manual', 'instruction', 'explain', 'comment', 'docstring',
            'reference', 'api docs', 'help text', 'tooltip'
        ],
        'task': [
            'task', 'todo', 'to-do', 'implement', 'create', 'setup', 'configure',
            'deploy', 'release', 'update', 'migrate', 'install', 'prepare',
            'organize', 'plan', 'schedule'
        ]
    }
    
    PRIORITY_KEYWORDS = {
        'critical': [
            'critical', 'urgent', 'emergency', 'immediately', 'asap', 'production down',
            'security', 'vulnerability', 'exploit', 'data loss', 'cannot access',
            'severe', 'catastrophic', 'show stopper', 'blocker', 'down'
        ],
        'high': [
            'high priority', 'important', 'blocking', 'severe', 'major', 
            'affects many', 'customer facing', 'deadline', 'soon', 'priority',
            'must fix', 'needed', 'required'
        ],
        'medium': [
            'medium', 'moderate', 'normal', 'should fix', 'inconvenient',
            'would be good', 'affects some', 'non-critical'
        ],
        'low': [
            'low priority', 'minor', 'trivial', 'nice to have', 'cosmetic',
            'eventually', 'someday', 'when possible', 'polish', 'small'
        ]
    }
    
    @staticmethod
    def preprocess_text(text: str) -> str:
        """Clean and normalize text for analysis"""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters but keep spaces and question marks
        text = re.sub(r'[^\w\s?]', ' ', text)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
    
    @classmethod
    def classify_category(cls, title: str, description: str) -> Tuple[str, float]:
        """
        Classify issue category based on title and description
        
        Args:
            title: Issue title
            description: Issue description
            
        Returns:
            Tuple of (category, confidence_score)
            where confidence_score is between 0 and 1
        """
        # Preprocess text
        title_text = cls.preprocess_text(title)
        desc_text = cls.preprocess_text(description)
        combined_text = f"{title_text} {desc_text}"
        
        # Initialize scores
        scores = {category: 0 for category in cls.CATEGORY_KEYWORDS.keys()}
        
        # Count keyword matches
        for category, keywords in cls.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                # Check if keyword exists in text
                if keyword in combined_text:
                    # Title matches are weighted higher (2x)
                    if keyword in title_text:
                        scores[category] += 2
                    else:
                        scores[category] += 1
        
        # If no matches found, default to 'task'
        if max(scores.values()) == 0:
            return 'task', 0.3
        
        # Get category with highest score
        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]
        
        # Calculate confidence (0-1)
        total_score = sum(scores.values())
        confidence = best_score / total_score if total_score > 0 else 0
        
        # Boost confidence if multiple keywords match
        if best_score >= 3:
            confidence = min(confidence * 1.2, 1.0)
        
        # Boost confidence if keyword found in title
        if any(kw in title_text for kw in cls.CATEGORY_KEYWORDS[best_category]):
            confidence = min(confidence * 1.1, 1.0)
        
        return best_category, round(confidence, 2)
    
    @classmethod
    def suggest_priority(cls, title: str, description: str) -> str:
        """
        Suggest priority based on keywords
        
        Args:
            title: Issue title
            description: Issue description
            
        Returns:
            Priority string ('low', 'medium', 'high', 'critical')
        """
        combined_text = cls.preprocess_text(f"{title} {description}")
        
        # Check priorities from highest to lowest
        for priority in ['critical', 'high', 'medium', 'low']:
            keywords = cls.PRIORITY_KEYWORDS[priority]
            for keyword in keywords:
                if keyword in combined_text:
                    return priority
        
        return 'medium'  # Default priority
    
    @classmethod
    def extract_keywords(cls, text: str, top_n: int = 5) -> List[str]:
        """
        Extract top keywords from text
        
        Args:
            text: Text to analyze
            top_n: Number of top keywords to return
            
        Returns:
            List of top keywords
        """
        text = cls.preprocess_text(text)
        words = text.split()
        
        # Common stop words to exclude
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these',
            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which',
            'who', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
            'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
            'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'now'
        }
        
        # Count word frequency
        word_freq = {}
        for word in words:
            if len(word) > 3 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Sort by frequency and return top N
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:top_n]]
    
    @classmethod
    def analyze_sentiment(cls, text: str) -> str:
        """
        Simple sentiment analysis (positive, neutral, negative)
        
        Args:
            text: Text to analyze
            
        Returns:
            Sentiment string
        """
        text = cls.preprocess_text(text)
        
        positive_words = ['good', 'great', 'excellent', 'awesome', 'love', 'perfect', 
                         'best', 'wonderful', 'fantastic', 'amazing']
        negative_words = ['bad', 'terrible', 'awful', 'hate', 'worst', 'horrible',
                         'disappointing', 'frustrating', 'annoying', 'useless']
        
        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'