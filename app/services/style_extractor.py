from loguru import logger
from collections import Counter
from statistics import mean
from typing import List, Dict

from app.ml.spacy_loader import get_nlp

NIGERIAN_MARKERS = ["na so", "abeg", "omo", "no wahala", "how far", "wahala dey", "ehen", "sha", "kpele", "yanga"]
NIGERIAN_CITIES = ["Lagos", "Ikeja", "Lekki", "Surulere", "Victoria Island", "Abuja", "Ibadan", "Port Harcourt", "Kano"]

def extract_style_fingerprint(corpus: str) -> dict:
    """
    Extract linguistic style metrics, POS distribution, top phrases, 
    Nigerian markers, and frequent entities from a text corpus.
    """
    if not corpus:
        return {}

    nlp = get_nlp()
    if nlp is None:
        logger.error("[StyleExtractor] NLP model not available.")
        return {}

    # spaCy has a default limit of 1,000,000 characters. 
    # We truncate to 100k as requested for performance.
    doc = nlp(corpus[:100000])
    
    # a. Sentence metrics
    sentences = list(doc.sents)
    avg_sentence_length = mean(len(sent) for sent in sentences) if sentences else 12.0
    exclamation_ratio = sum(1 for sent in sentences if "!" in sent.text) / len(sentences) if sentences else 0.0
    
    # b. Formality score
    # Count nouns and adjectives vs total significant POS tags
    pos_counts = Counter(token.pos_ for token in doc if not token.is_stop and not token.is_punct)
    total_pos = sum(pos_counts.values())
    
    # formality = (NOUN + ADJ) / total
    formality_score = (pos_counts.get("NOUN", 0) + pos_counts.get("ADJ", 0)) / total_pos if total_pos else 0.5
    
    # c. POS distribution
    pos_distribution = {tag: count/total_pos for tag, count in pos_counts.items()} if total_pos else {}
    
    # d. Top phrases (Noun chunks and bigrams)
    # Extract noun chunks (multi-word)
    noun_chunks = [chunk.text.lower().strip() for chunk in doc.noun_chunks if len(chunk.text.split()) >= 2]
    
    # Extract bigrams
    tokens = [token.text.lower() for token in doc if not token.is_stop and not token.is_punct and not token.is_space]
    bigrams = [" ".join(tokens[i:i+2]) for i in range(len(tokens)-1)]
    
    top_phrases_counter = Counter(noun_chunks + bigrams)
    top_phrases = [phrase for phrase, count in top_phrases_counter.most_common(10)]
    
    # e. Nigerian markers
    corpus_lower = corpus.lower()
    found_markers = [marker for marker in NIGERIAN_MARKERS if marker in corpus_lower]
    
    # f. Favorite entities
    # PERSON, GPE, ORG, PRODUCT, EXPRESSION (from our EntityRuler)
    interesting_labels = {"PERSON", "GPE", "ORG", "PRODUCT", "EXPRESSION"}
    entities = [
        ent.text.strip() for ent in doc.ents 
        if ent.label_ in interesting_labels and len(ent.text.strip()) > 2
    ]
    favorite_entities = [ent for ent, count in Counter(entities).most_common(10)]
    
    # g. Nigerian locations
    nigerian_locations = list(set([
        ent.text.strip() for ent in doc.ents 
        if ent.label_ == "GPE" and ent.text.strip() in NIGERIAN_CITIES
    ]))

    return {
        "avg_sentence_length": float(avg_sentence_length),
        "exclamation_ratio": float(exclamation_ratio),
        "formality_score": float(formality_score),
        "pos_distribution": pos_distribution,
        "top_phrases": top_phrases,
        "nigerian_markers": found_markers,
        "favorite_entities": favorite_entities,
        "nigerian_locations": nigerian_locations
    }
