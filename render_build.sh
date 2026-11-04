#!/usr/bin/env bash
# Render build command:  bash render_build.sh
#
# 1. installs the packages,
# 2. downloads the ONNX copy of the embedding model (same model and revision as phase 3), which
#    answers questions without PyTorch so the site fits Render's 512 MB plan,
# 3. rebuilds the phase 4 vector store from the committed excerpts (Data/chunks/chunks.jsonl) and
#    their phase 3 vectors (Data/embeddings/), so nothing is re-embedded and no model is needed.
# Set EMBEDDING_BACKEND=onnx and MISTRAL_API_KEY in the service's environment.
set -euo pipefail
pip install -r requirements.txt
cd Code
python -m src.phase3_embedding.onnx_model
python -m src.phase4_vector_store.run
