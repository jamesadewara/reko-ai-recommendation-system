import spacy
from loguru import logger
from spacy.language import Language
from app.core.config import settings

_nlp = None

def get_nlp() -> Language:
    """
    Singleton pattern for loading the spaCy model with a custom Nigerian Entity Ruler.
    """
    global _nlp
    if _nlp is not None:
        return _nlp

    try:
        logger.info(f"[NLP] Loading spaCy model: {settings.SPACY_MODEL}")
        nlp = spacy.load(settings.SPACY_MODEL)
        
        # Add EntityRuler BEFORE the ner pipe
        if "entity_ruler" not in nlp.pipe_names:
            logger.info("[NLP] Adding Nigerian EntityRuler to pipe.")
            ruler = nlp.add_pipe("entity_ruler", before="ner")
            patterns = [
                # Nigerian cities
                {"label": "GPE", "pattern": "Lagos"},
                {"label": "GPE", "pattern": "Ikeja"},
                {"label": "GPE", "pattern": "Lekki"},
                {"label": "GPE", "pattern": "Surulere"},
                {"label": "GPE", "pattern": "Victoria Island"},
                {"label": "GPE", "pattern": "Abuja"},
                {"label": "GPE", "pattern": "Ibadan"},
                {"label": "GPE", "pattern": "Port Harcourt"},
                {"label": "GPE", "pattern": "Kano"},
                # Nigerian cultural entities
                {"label": "ORG", "pattern": "Nollywood"},
                {"label": "ORG", "pattern": "Afrobeats"},
                {"label": "ORG", "pattern": "Nigerian"},
                {"label": "PRODUCT", "pattern": [{"LOWER": "jollof"}, {"LOWER": "rice"}]},
                {"label": "PRODUCT", "pattern": [{"LOWER": "pounded"}, {"LOWER": "yam"}]},
                {"label": "PRODUCT", "pattern": [{"LOWER": "amala"}]},
                {"label": "PRODUCT", "pattern": [{"LOWER": "egusi"}]},
                {"label": "PRODUCT", "pattern": [{"LOWER": "suya"}]},
                {"label": "PRODUCT", "pattern": [{"LOWER": "eba"}]},
                {"label": "PRODUCT", "pattern": [{"LOWER": "fufu"}]},
                # Pidgin expressions as entities for tracking
                {"label": "EXPRESSION", "pattern": [{"LOWER": "na"}, {"LOWER": "so"}]},
                {"label": "EXPRESSION", "pattern": [{"LOWER": "no"}, {"LOWER": "wahala"}]},
                {"label": "EXPRESSION", "pattern": [{"LOWER": "how"}, {"LOWER": "far"}]},
            ]
            ruler.add_patterns(patterns)
        
        _nlp = nlp
        return _nlp

    except Exception as e:
        import traceback
        logger.error(f"[NLP] Failed to load spaCy model {settings.SPACY_MODEL}: {e}")
        logger.error(traceback.format_exc())
        return None
