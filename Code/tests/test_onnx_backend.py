"""The ONNX question step (EMBEDDING_BACKEND=onnx, used on Render) must make the same vectors as
the PyTorch model that built the corpus, or questions would not match the stored excerpts."""
import numpy as np
import pytest

from src import config
from src.phase3_embedding.embedder import Embedder

needs_model = pytest.mark.skipif(not (config.ONNX_MODEL_DIR / "onnx" / "model.onnx").exists(),
                                 reason="ONNX model not downloaded (python -m src.phase3_embedding.onnx_model)")


@needs_model
def test_onnx_vectors_match_the_pytorch_model():
    texts = ["What leads investors to pause, reduce or stop a SIP?", "sip",
             "My SIP instalment failed but the money was debited. " * 40]  # the last is over the 256-token cut
    torch_vectors = Embedder(backend="torch").embed(texts)
    onnx_vectors = Embedder(backend="onnx").embed(texts)
    assert onnx_vectors.shape == (3, config.EMBEDDING_DIM) and onnx_vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(onnx_vectors, axis=1), 1, atol=1e-5)
    assert (torch_vectors * onnx_vectors).sum(axis=1).min() > 0.99999


def test_backend_is_chosen_per_embedder():
    assert Embedder(backend="onnx").backend == "onnx" and Embedder(backend="torch").backend == "torch"
    assert Embedder().backend == config.EMBEDDING_BACKEND
