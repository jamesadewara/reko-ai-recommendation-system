python -m pip install -r requirements.txt --no-deps
# Run after install: python -m spacy download en_core_web_sm
# For Nigerian NER bonus: python -m spacy download en_core_web_md (better NER)
# After pip install -r requirements.txt, run:
python -m spacy download en_core_web_sm
# Optional but recommended for better entity recognition:
python -m spacy download en_core_web_md