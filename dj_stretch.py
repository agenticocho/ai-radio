#!/usr/bin/env python3
"""
dj_stretch.py  —  Agent DJ Step 2: BPM/key-matched time-stretch + pitch-shift
Usage: python3 dj_stretch.py <classical_track.mp3> <electronic_track.mp3> <output.mp3>

Classical is the tempo/key reference. Electronic is stretched to match.
"""

import sys
import os
import tempfile
import subprocess
import numpy as np
import librosa
import pyrubberband as pyrb
import soundfile as sf

BPM_RATIO_MIN = 0.6
BPM_RATIO_MAX = 1.6

CHROMA_TO_KEY = ['C', 'C#', 'D', 'D#', 'E', 'F',
                 'F#', 'G', 'G#', 'A', 'A#', 'B']

def load_audio(path, sr=44100):
    """Load any audio file to numpy array via ffmpeg decode → soundfile."""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_wav = tmp.name
    subprocess.run(
        ['ffmpeg', '-y', '-i', path,
         '-ar', str(sr), '-ac', '2', '-f', 'wav', tmp_wav],
        check=True, capture_output=True
    )
    y, sr_file = sf.read(tmp_wav, always_2d=True)
    os.unlink(tmp_wav)
    return y.T, sr_file  # shape: (2, samples)

def detect_bpm(y, sr):
    y_mono = librosa.to_mono(y)
    tempo, _ = librosa.beat.beat_track(y=y_mono, sr=sr)
    return float(np.atleast_1d(tempo)[0])

def detect_key(y, sr):
    y_mono = librosa.to_mono(y)
    chroma = librosa.feature.chroma_cqt(y=y_mono, sr=sr)
    key_idx = int(np.argmax(np.mean(chroma, axis=1)))
    return key_idx, CHROMA_TO_KEY[key_idx]

def semitone_distance(src_key, tgt_key):
    diff = (tgt_key - src_key) % 12
    if diff > 6:
        diff -= 12
    return diff

def stretch_and_pitch(y, sr, bpm_ratio, semitones):
    channels = []
    for ch in range(y.shape[0]):
        ch_audio = y[ch]
        stretched = pyrb.time_stretch(ch_audio, sr, bpm_ratio)
        if abs(semitones) > 0.1:
            stretched = pyrb.pitch_shift(stretched, sr, semitones)
        channels.append(stretched)
    max_len = max(len(c) for c in channels)
    channels = [np.pad(c, (0, max_len - len(c))) for c in channels]
    return np.stack(channels)

def audio_to_mp3(y, sr, out_path):
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_wav = tmp.name
    sf.write(tmp_wav, y.T, sr, subtype='PCM_16')
    subprocess.run(
        ['ffmpeg', '-y', '-i', tmp_wav, '-q:a', '2', out_path],
        check=True, capture_output=True
    )
    os.unlink(tmp_wav)

def main():
    if len(sys.argv) != 4:
        print("Usage: dj_stretch.py <classical.mp3> <electronic.mp3> <output.mp3>")
        sys.exit(1)

    classical_path, electronic_path, out_path = sys.argv[1:]
    SR = 44100

    print(f"[dj_stretch] Loading classical: {os.path.basename(classical_path)}")
    classical_audio, sr = load_audio(classical_path, SR)
    classical_bpm = detect_bpm(classical_audio, sr)
    # BPM sanity clamp
    while classical_bpm > 160: classical_bpm /= 2
    while classical_bpm < 40:  classical_bpm *= 2
    classical_key_idx, classical_key = detect_key(classical_audio, sr)
    print(f"  -> BPM: {classical_bpm:.1f}  Key: {classical_key}")

    print(f"[dj_stretch] Loading electronic: {os.path.basename(electronic_path)}")
    elec_audio, sr = load_audio(electronic_path, SR)
    elec_bpm = detect_bpm(elec_audio, sr)
    while elec_bpm > 160: elec_bpm /= 2
    while elec_bpm < 40:  elec_bpm *= 2
    elec_key_idx, elec_key = detect_key(elec_audio, sr)
    print(f"  -> BPM: {elec_bpm:.1f}  Key: {elec_key}")

    ratio = classical_bpm / elec_bpm
    semitones = semitone_distance(elec_key_idx, classical_key_idx)
    print(f"[dj_stretch] Stretch ratio: {ratio:.3f}  Pitch shift: {semitones:+d} semitones")

    if not (BPM_RATIO_MIN <= ratio <= BPM_RATIO_MAX):
        print(f"  WARNING: REJECTED -- ratio {ratio:.2f} outside safe range "
              f"[{BPM_RATIO_MIN}, {BPM_RATIO_MAX}]")
        print(f"  Classical {classical_bpm:.1f} BPM + Electronic {elec_bpm:.1f} BPM = incompatible pairing.")
        sys.exit(2)

    print(f"[dj_stretch] Stretching electronic track...")
    stretched = stretch_and_pitch(elec_audio, sr, ratio, semitones)

    print(f"[dj_stretch] Writing output: {out_path}")
    audio_to_mp3(stretched, sr, out_path)

    meta_path = out_path + '.meta'
    with open(meta_path, 'w') as f:
        f.write(f"classical_bpm={classical_bpm:.1f}\n")
        f.write(f"electronic_bpm={elec_bpm:.1f}\n")
        f.write(f"stretch_ratio={ratio:.4f}\n")
        f.write(f"pitch_semitones={semitones}\n")
        f.write(f"classical_key={classical_key}\n")
        f.write(f"electronic_key={elec_key}\n")

    print(f"[dj_stretch] Done. Output: {out_path}  Metadata: {meta_path}")
    print(f"  Classical {classical_bpm:.1f} BPM ({classical_key}) -> "
          f"Electronic stretched to match (was {elec_bpm:.1f} BPM, {elec_key})")

if __name__ == '__main__':
    main()
