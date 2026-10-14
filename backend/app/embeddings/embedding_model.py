
from functools import lru_cache

from sentence_transformers import SentenceTransformer

# --------------------------------------------------
# Model configuration
# --------------------------------------------------

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_BATCH_SIZE = 32


# --------------------------------------------------
# Load model once and reuse it
# --------------------------------------------------

@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load the embedding model once per application process."""
    return SentenceTransformer(MODEL_NAME)


# --------------------------------------------------
# Validate input text
# --------------------------------------------------

def _clean_text(text: str) -> str:
    if text is None:
        raise ValueError("Embedding input cannot be None.")

    if not isinstance(text, str):
        raise TypeError("Embedding input must be a string.")

    cleaned_text = text.strip()

    if not cleaned_text:
        raise ValueError("Embedding input cannot be empty.")

    return cleaned_text


# --------------------------------------------------
# Create embeddings for multiple documents
# --------------------------------------------------

def create_embeddings(texts: list[str]) -> list[list[float]]:
    """Convert multiple text documents into normalized vectors."""
    if not isinstance(texts, list):
        raise TypeError("texts must be a list of strings.")

    if not texts:
        return []

    cleaned_texts = [_clean_text(text) for text in texts]

    model = get_embedding_model()

    embeddings = model.encode(
        cleaned_texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    result = embeddings.tolist()

    if len(result) != len(cleaned_texts):
        raise RuntimeError(
            "Embedding count does not match document count."
        )

    return result


# --------------------------------------------------
# Create embedding for one document
# --------------------------------------------------

def create_embedding(text: str) -> list[float]:
    """Convert one text document into a normalized vector."""
    cleaned_text = _clean_text(text)

    model = get_embedding_model()

    embedding = model.encode(
        cleaned_text,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    return embedding.tolist()
