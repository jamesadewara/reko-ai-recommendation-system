import time
from typing import Dict
from loguru import logger

try:
    from bert_score import score
    BERTSCORE_AVAILABLE = True
except ImportError:
    BERTSCORE_AVAILABLE = False
    logger.warning("[BERTScore] bert_score library not found. Falling back to heuristic.")

class BERTScoreEvaluator:
    def __init__(self):
        pass

    def evaluate(self, generated_review: str, user_corpus: str) -> dict:
        """
        Evaluate the semantic similarity between the generated review 
        and the user's real online corpus.
        """
        if not user_corpus or len(user_corpus) < 50:
            return {
                "bertscore_f1": 0.75, 
                "precision": 0.75, 
                "recall": 0.75, 
                "note": "insufficient_corpus"
            }

        if not BERTSCORE_AVAILABLE:
            return self._heuristic_fallback(generated_review, user_corpus)

        try:
            start_time = time.time()
            
            # Use a chunk of the corpus to avoid OOM and long delays on CPU
            reference_text = user_corpus[:1000]
            
            # bert_score.score returns (P, R, F1)
            P, R, F1 = score(
                [generated_review],
                [reference_text],
                lang="en",
                model_type="microsoft/deberta-xlarge-mnli", # Large but high quality
                device="cpu"
            )
            
            elapsed = time.time() - start_time
            logger.info(f"[BERTScore] Evaluation complete in {elapsed:.2f}s")
            
            # If it takes too long (> 10s), we might want to log a warning for future runs
            if elapsed > 10:
                logger.warning("[BERTScore] Evaluation took over 10s on CPU.")

            return {
                "bertscore_f1": float(F1[0]),
                "precision": float(P[0]),
                "recall": float(R[0])
            }

        except Exception as e:
            logger.error(f"[BERTScore] Failed to evaluate: {e}")
            return self._heuristic_fallback(generated_review, user_corpus)

    def _heuristic_fallback(self, review: str, corpus: str) -> dict:
        """
        A fast fallback that computes vocabulary overlap as a proxy for similarity.
        """
        review_words = set(review.lower().split())
        corpus_words = set(corpus.lower()[:5000].split())
        
        overlap = len(review_words.intersection(corpus_words))
        score_val = 0.7 + (min(overlap, 20) / 100) # Heuristic between 0.7 and 0.9
        
        return {
            "bertscore_f1": score_val,
            "precision": score_val,
            "recall": score_val,
            "note": "heuristic_fallback"
        }
