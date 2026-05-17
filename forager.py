#!/usr/bin/env python3
"""
forager.py — Agent DJ Step 3: autonomous track downloader
Sources: Musopen API (Classical), Free Music Archive (Downtempo), Internet Archive (both)
Usage: python3 forager.py --output-dir <dir> --log <logfile> [--max-downloads N]
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

PYTHON = "/opt/homebrew/Caskroom/miniforge/base/bin/python3"
DJ_STRETCH = Path("~/cabinet-dj/ai-radio/dj_stretch.py").expanduser()

SOURCES = {
    "musopen_classical": {
        "url": "https://api.musopen.org/recordings?format=mp3&limit=10&license=by,by-nc,cc0&skip=0",
        "genre": "classical",
        "parser": "musopen"
    },
    "fma_downtempo": {
        "url": "https://freemusicarchive.org/api/get/tracks.json?genre_id=98&limit=10&page=1&api_key=free",
        "genre": "electronic",
        "parser": "fma"
    },
    "archive_classical": {
        "url": "https://archive.org/advancedsearch.php?q=subject%3Aclassical+mediatype%3Aaudio+format%3AMP3&fl=identifier,title,creator&rows=10&output=json",
        "genre": "classical",
        "parser": "archive"
    }
}


def get_existing_slugs(output_dir):
    return {p.stem for p in Path(output_dir).glob("*.mp3")}


def fetch_json(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentDJ/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def parse_musopen(data):
    """Returns list of {title, url, slug} dicts."""
    tracks = []
    for r in data.get("recordings", data if isinstance(data, list) else []):
        url = r.get("file") or r.get("url", "")
        if not url or not url.endswith(".mp3"):
            continue
        title = r.get("name", "unknown").replace("/", "_").replace(" ", "_")[:60]
        slug = f"classical_musopen_{title}"
        tracks.append({"title": title, "url": url, "slug": slug})
    return tracks


def parse_fma(data):
    tracks = []
    for t in data.get("dataset", []):
        url = t.get("track_file", "")
        if not url:
            continue
        title = t.get("track_title", "unknown").replace("/", "_").replace(" ", "_")[:60]
        # Skip vocal tracks
        tags = t.get("track_tags", "").lower()
        if any(w in tags for w in ["vocal", "voice", "sung", "lyrics"]):
            continue
        slug = f"electronic_fma_{title}"
        tracks.append({"title": title, "url": url, "slug": slug})
    return tracks


def parse_archive(data):
    tracks = []
    for doc in data.get("response", {}).get("docs", []):
        ident = doc.get("identifier", "")
        title = doc.get("title", "unknown").replace("/", "_").replace(" ", "_")[:60]
        # Archive.org: construct a plausible mp3 URL (will need yt-dlp for actual download)
        slug = f"classical_archive_{ident}"
        tracks.append({"title": title, "url": f"https://archive.org/details/{ident}", "slug": slug})
    return tracks


def download_track(url, dest_path, use_ytdlp=False):
    """Download a track. Returns True on success."""
    if use_ytdlp or "archive.org/details" in url:
        result = subprocess.run(
            [PYTHON, "-m", "yt_dlp", "-x", "--audio-format", "mp3",
             "--audio-quality", "5", "-o", str(dest_path), url],
            capture_output=True, timeout=120
        )
        return result.returncode == 0
    else:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AgentDJ/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if len(data) < 1_000_000:  # < 1MB = likely an error page
                return False
            with open(dest_path, "wb") as f:
                f.write(data)
            return True
        except Exception:
            return False


def tag_with_bpm(mp3_path):
    """Run dj_stretch BPM detection only (pass same file for both args as a BPM probe)."""
    meta_path = str(mp3_path) + ".meta"
    # Use a simple librosa probe instead of dj_stretch (which needs two tracks)
    probe_script = f"""
import librosa, numpy as np, sys
CHROMA = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
try:
    y, sr = librosa.load('{mp3_path}', sr=22050, mono=True, duration=60)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo)
    if bpm > 160: bpm /= 2
    if bpm < 40: bpm *= 2
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key = CHROMA[int(np.argmax(np.mean(chroma, axis=1)))]
    print(f"bpm={{bpm:.1f}}\\nkey={{key}}")
except Exception as e:
    print(f"bpm=0.0\\nkey=?\\nerror={{e}}")
"""
    result = subprocess.run([PYTHON, "-c", probe_script], capture_output=True, text=True, timeout=90)
    with open(meta_path, "w") as f:
        f.write(result.stdout)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--max-downloads", type=int, default=5)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log)

    existing = get_existing_slugs(output_dir)
    downloaded = 0
    report_lines = []

    for source_name, config in SOURCES.items():
        if downloaded >= args.max_downloads:
            break

        data = fetch_json(config["url"])
        if "error" in data:
            report_lines.append(f"[WARN] {source_name}: {data['error']}")
            continue

        parser_fn = {"musopen": parse_musopen, "fma": parse_fma, "archive": parse_archive}[config["parser"]]
        tracks = parser_fn(data)

        for track in tracks:
            if downloaded >= args.max_downloads:
                break
            slug = track["slug"]
            if slug in existing:
                continue

            dest = output_dir / f"{slug}.mp3"
            use_ytdlp = config["parser"] == "archive"

            success = download_track(track["url"], dest, use_ytdlp=use_ytdlp)
            if not success:
                report_lines.append(f"[FAIL] {slug}")
                continue

            meta = tag_with_bpm(dest)
            existing.add(slug)
            downloaded += 1
            report_lines.append(f"[OK] {slug} | {meta.replace(chr(10), ' | ')}")
            time.sleep(1)  # rate limit courtesy pause

    # Write log
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"\n=== {timestamp} | +{downloaded} files ===\n")
        for line in report_lines:
            f.write(line + "\n")

    # Print summary to stdout (Cabinet agent reads this)
    total_mp3s = list(output_dir.glob("*.mp3"))
    classical = [p for p in total_mp3s if "classical" in p.name]
    electronic = [p for p in total_mp3s if "electronic" in p.name]

    print(f"Downloaded this run: {downloaded}")
    print(f"Total in audio/: {len(total_mp3s)} files ({len(classical)} classical, {len(electronic)} electronic)")
    for line in report_lines:
        print(line)


if __name__ == "__main__":
    main()