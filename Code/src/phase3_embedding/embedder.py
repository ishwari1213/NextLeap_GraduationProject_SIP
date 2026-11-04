"""The one place vectors are made: excerpts and sections here (phase 3), questions in phase 5.

Both sides must use the same model and the same normalisation, or their vectors cannot be
compared (architecture section 6), so phase 5 imports this class instead of building its own.
"""
from __future__ import annotations

import logging

import numpy as np

from src import config

log = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str | None = None, device: str | None = None, batch_size: int | None = None,
                 backend: str | None = None):
        self.model_name = model_name or config.EMBEDDING_MODEL
        self.device = device or config.EMBEDDING_DEVICE
        self.batch_size = batch_size or config.EMBEDDING_BATCH_SIZE
        self.backend = backend or config.EMBEDDING_BACKEND
        self._model = None

    def _load(self):
        if self.backend == "onnx":  # same model without PyTorch, for a small deployment (onnx_model.py)
            from src.phase3_embedding.onnx_model import OnnxMiniLM
            return OnnxMiniLM()
        from sentence_transformers import SentenceTransformer
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
        hf_logging.disable_progress_bar()
        try:  # the cached copy, without asking the Hugging Face hub; download only if missing
            model = SentenceTransformer(self.model_name, device=self.device, local_files_only=True)
        except (OSError, ValueError):
            log.info("Model not cached; downloading %s", self.model_name)
            model = SentenceTransformer(self.model_name, device=self.device)
        model.max_seq_length = config.MODEL_MAX_TOKENS
        dim = model.get_embedding_dimension() if hasattr(model, "get_embedding_dimension") \
            else model.get_sentence_embedding_dimension()
        if dim != config.EMBEDDING_DIM:
            raise ValueError(f"{self.model_name} makes {dim}-d vectors; config expects {config.EMBEDDING_DIM}")
        return model

    @property
    def model(self):
        if self._model is None:
            self._model = self._load()
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        """Unit-length float32 vectors, one row per text, so cosine similarity is a dot product."""
        if not texts:
            return np.zeros((0, config.EMBEDDING_DIM), dtype=np.float32)
        vectors = self.model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)
