#!/usr/bin/env python3
"""Download HF YOLO model to models/ ."""
from pathlib import Path
from app.config import settings

def main(force: bool = False):
    target = Path(settings.yolo_model_path)
    print(f"Target: {target}")
    print(f"HF repo: {settings.yolo_hf_repo} / {settings.yolo_hf_filename}")
    if target.exists() and not force:
        print(f"Already exists ({target.stat().st_size/1e6:.1f} MB), use --force to re-download")
        return
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("pip install huggingface_hub")
        raise
    target.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading...")
    cached = hf_hub_download(repo_id=settings.yolo_hf_repo, filename=settings.yolo_hf_filename)
    import shutil
    shutil.copyfile(cached, target)
    print(f"Saved to {target} ({target.stat().st_size/1e6:.1f} MB)")
    # verify load
    try:
        from ultralytics import YOLO
        m = YOLO(str(target))
        print(f"YOLO loaded, labels: {m.names}")
    except Exception as e:
        print(f"YOLO load failed: {e}")

if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)
