#!/usr/bin/env bash
# Download the Piper TTS voice model (en_US-lessac-medium, ~60MB)
set -e

MODEL_DIR="audio"
MODEL_NAME="en_US-lessac-medium"
BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"

mkdir -p "$MODEL_DIR"

echo "Downloading Piper voice model: $MODEL_NAME"
curl -L -o "$MODEL_DIR/${MODEL_NAME}.onnx" \
    "${BASE_URL}/${MODEL_NAME}.onnx"

curl -L -o "$MODEL_DIR/${MODEL_NAME}.onnx.json" \
    "${BASE_URL}/${MODEL_NAME}.onnx.json"

echo "Done. Model saved to $MODEL_DIR/${MODEL_NAME}.onnx"
touch audio/.gitkeep
