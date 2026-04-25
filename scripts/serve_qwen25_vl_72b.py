from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Qwen2.5-VL-72B 4-bit via mlx_vlm without autoreload.")
    parser.add_argument(
        "--model",
        default=os.environ.get("QWEN25_VL_MODEL_PATH", "Qwen2.5-VL-72B-Instruct-4bit-MLX"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--prefill-step-size", type=int, default=256)
    parser.add_argument("--trust-remote-code", action="store_true")
    args = parser.parse_args()

    os.environ["PRELOAD_MODEL"] = args.model
    os.environ["PREFILL_STEP_SIZE"] = str(args.prefill_step_size)
    if args.trust_remote_code:
        os.environ["MLX_TRUST_REMOTE_CODE"] = "true"

    uvicorn.run("mlx_vlm.server:app", host=args.host, port=args.port, workers=1, reload=False)


if __name__ == "__main__":
    main()
