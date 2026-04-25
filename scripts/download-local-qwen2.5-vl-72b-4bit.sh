#!/bin/zsh
set -euo pipefail

PYTHON_BIN=${PYTHON_BIN:-${LOCAL_QWEN_PYTHON_BIN:-python}}
MODEL_REPO=${MODEL_REPO:-mlx-community/Qwen2.5-VL-72B-Instruct-4bit}
TARGET_DIR=${TARGET_DIR:-${QWEN25_VL_MODEL_PATH:-Qwen2.5-VL-72B-Instruct-4bit-MLX}}
HF_ENDPOINT=${HF_ENDPOINT:-https://hf-mirror.com}
MAX_WORKERS=${MAX_WORKERS:-2}
RETRY_SECONDS=${RETRY_SECONDS:-10}
MAX_ATTEMPTS=${MAX_ATTEMPTS:-0}

export MODEL_REPO TARGET_DIR HF_ENDPOINT MAX_WORKERS RETRY_SECONDS MAX_ATTEMPTS

exec "$PYTHON_BIN" - <<'PY'
import os
import time

from huggingface_hub import snapshot_download

repo_id = os.environ["MODEL_REPO"]
target_dir = os.environ["TARGET_DIR"]
endpoint = os.environ["HF_ENDPOINT"]
max_workers = int(os.environ["MAX_WORKERS"])
retry_seconds = int(os.environ["RETRY_SECONDS"])
max_attempts = int(os.environ["MAX_ATTEMPTS"])

print(f"Downloading {repo_id} -> {target_dir}")
print(f"Using endpoint: {endpoint}")
attempt = 1
while True:
    try:
        print(f"Attempt {attempt} with max_workers={max_workers}")
        snapshot_download(
            repo_id=repo_id,
            local_dir=target_dir,
            endpoint=endpoint,
            max_workers=max_workers,
        )
        print("Download complete.")
        break
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"Download attempt {attempt} failed: {exc}")
        if max_attempts and attempt >= max_attempts:
            raise
        attempt += 1
        print(f"Retrying in {retry_seconds}s...")
        time.sleep(retry_seconds)
PY
