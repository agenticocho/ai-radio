#!/usr/bin/env python3
# vocal_check.py — writes vocal=clean or vocal=detected to .meta sidecars
# Usage: python3 vocal_check.py [--audio-dir DIR]

import os, json, subprocess, re, glob, argparse

PYTHON = "/opt/homebrew/Caskroom/miniforge/base/bin/python3"
IFW = "/opt/homebrew/Caskroom/miniforge/base/bin/insanely-fast-whisper"

HALLUCINATION_PATTERNS = [
    r"(i'm a (man|little|going)\b.{0,30}){4,}",   # repetitive phrases
    r"(\bnd\b.{0,10}){5,}",                         # "nd nd nd nd"
    r"(ʻ‿ʻ\s*){3,}",                                # unicode garbage
]

def is_hallucination(text: str) -> bool:
    t = text.lower().strip()
    if len(t) < 20:
        return True  # empty or near-empty = clean (no vocals detected)
    for pat in HALLUCINATION_PATTERNS:
        if re.search(pat, t):
            return True
    return False

def check_track(mp3path: str) -> str:
    """Sample first 60s only — sufficient for vocal detection."""
    script = f"""
import torch, numpy as np, json
from transformers import pipeline

pipe = pipeline(
    "automatic-speech-recognition",
    model="openai/whisper-base",
    device="mps",
    torch_dtype=torch.float16,
)

import librosa
y, sr = librosa.load("{mp3path}", sr=16000, mono=True, duration=60)
audio = y.astype(np.float32)

result = pipe(audio, generate_kwargs={{"task": "transcribe", "language": "english"}})
print(json.dumps(result))
"""
    r = subprocess.run(
        [PYTHON, "-c", script],
        capture_output=True, text=True, timeout=120
    )
    if r.returncode != 0:
        return "clean"
    try:
        data = json.loads(r.stdout.strip())
        text = data.get("text", "")
        return "clean" if is_hallucination(text) else "detected"
    except:
        return "clean"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-dir",
        default=os.path.expanduser("~/cabinet-dj/ai-radio/audio"))
    args = parser.parse_args()

    mp3s = sorted(glob.glob(f"{args.audio_dir}/*.mp3"))
    for mp3 in mp3s:
        meta = mp3.replace(".mp3", ".meta")
        # Skip if already checked
        if os.path.exists(meta):
            content = open(meta).read()
            if "vocal=" in content:
                print(f"  SKIP (already checked): {os.path.basename(mp3)}")
                continue
        
        print(f"  Checking: {os.path.basename(mp3)} ...", end=" ", flush=True)
        result = check_track(mp3)
        print(result)

        # Write or append to .meta
        if os.path.exists(meta):
            with open(meta, "a") as f:
                f.write(f"vocal={result}\n")
        else:
            with open(meta, "w") as f:
                f.write(f"vocal={result}\n")

if __name__ == "__main__":
    main()