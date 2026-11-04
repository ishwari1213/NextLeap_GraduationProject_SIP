"""The phase 3 model run with onnxruntime instead of PyTorch, for small deployments.

Same model and revision (sentence-transformers/all-MiniLM-L6-v2, config.EMBEDDING_MODEL_REVISION),
its official ONNX export, the same tokenizer, the same 256-token cut, mean pooling and unit
length, so question vectors match the PyTorch ones and can be compared with the stored corpus
vectors. It needs onnxruntime and tokenizers (both installed with chromadb), not PyTorch, which
keeps a 512 MB host within its memory. Used when EMBEDDING_BACKEND=onnx (see embedder.py).

Download the model files once, at build time (run from the Code/ folder):
    python -m src.phase3_embedding.onnx_model
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from src import config

FILES = ("onnx/model.onnx", "tokenizer.json")


def download(target: Path | None = None) -> Path:
    from huggingface_hub import hf_hub_download

    target = target or config.ONNX_MODEL_DIR
    for name in FILES:
        hf_hub_download(config.EMBEDDING_MODEL, name, revision=config.EMBEDDING_MODEL_REVISION, local_dir=target)
    return target


class OnnxMiniLM:
    """Implements the part of SentenceTransformer.encode that Embedder uses."""

    def __init__(self, model_dir: Path | None = None):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_dir = model_dir or config.ONNX_MODEL_DIR
        if not (model_dir / FILES[0]).exists():
            download(model_dir)
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=config.MODEL_MAX_TOKENS)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1  # a small host has a fraction of a CPU
        self.session = ort.InferenceSession(str(model_dir / FILES[0]), options, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}

    def encode(self, texts: list[str], batch_size: int = 32, normalize_embeddings: bool = True, **_) -> np.ndarray:
        out = []
        for start in range(0, len(texts), batch_size):
            encoded = self.tokenizer.encode_batch(texts[start:start + batch_size])
            mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            feed = {"input_ids": np.array([e.ids for e in encoded], dtype=np.int64), "attention_mask": mask,
                    "token_type_ids": np.array([e.type_ids for e in encoded], dtype=np.int64)}
            tokens = self.session.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0]
            weights = mask[..., None].astype(np.float32)
            pooled = (tokens * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)  # mean pooling
            if normalize_embeddings:
                pooled = pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
            out.append(pooled.astype(np.float32))
        return np.concatenate(out) if out else np.zeros((0, config.EMBEDDING_DIM), dtype=np.float32)


if __name__ == "__main__":
    path = download()
    print(f"{config.EMBEDDING_MODEL}@{config.EMBEDDING_MODEL_REVISION[:7]} (ONNX) -> "
          f"{path.relative_to(config.PROJECT_DIR).as_posix()}")
    sys.exit(0)
