#!/bin/bash
PYTHON=/opt/homebrew/Caskroom/miniforge/base/bin/python3
AUDIO=/Users/mikebird/cabinet-dj/ai-radio/audio
LOG=$AUDIO/curator.log

echo "$(date): curator.sh starting" >> $LOG

LATEST=$(ls -d /Users/mikebird/cabinet/.agents/.conversations/*dj-curator* 2>/dev/null | sort -r | head -1)
if [ -z "$LATEST" ]; then
  echo "$(date): No curator session found" >> $LOG; exit 0
fi
echo "$(date): Reading session $LATEST" >> $LOG

CLASSICAL=$($PYTHON /tmp/parse_curator.py | sed -n '1p')
ELECTRONIC=$($PYTHON /tmp/parse_curator.py | sed -n '2p')
NARRATION=$($PYTHON /tmp/parse_curator.py | sed -n '3p')

if [ -z "$CLASSICAL" ] || [ -z "$ELECTRONIC" ]; then
  echo "$(date): Could not parse pairing" >> $LOG
  head -3 "$LATEST/transcript.txt" >> $LOG
  exit 0
fi
echo "$(date): Pairing — $CLASSICAL + $ELECTRONIC" >> $LOG

[ -f "$AUDIO/$CLASSICAL" ] || { echo "$(date): MISSING $AUDIO/$CLASSICAL" >> $LOG; exit 1; }
[ -f "$AUDIO/$ELECTRONIC" ] || { echo "$(date): MISSING $AUDIO/$ELECTRONIC" >> $LOG; exit 1; }

$PYTHON /Users/mikebird/cabinet-dj/ai-radio/dj_stretch.py \
  "$AUDIO/$CLASSICAL" "$AUDIO/$ELECTRONIC" /tmp/dj_next.mp3 >> $LOG 2>&1
case $? in
  2) echo "$(date): Rejected by dj_stretch.py" >> $LOG; exit 0 ;;
  0) echo "$(date): Stretch OK → /tmp/dj_next.mp3" >> $LOG ;;
  *) echo "$(date): dj_stretch.py failed" >> $LOG; exit 1 ;;
esac

rm -rf /tmp/dj_narration.wav /tmp/dj_narration.mp3 /tmp/dj_chunks.txt
$PYTHON -m mlx_audio.tts.generate \
  --model mlx-community/Kokoro-82M-4bit \
  --voice af_sky \
  --text "$NARRATION" \
  --output /tmp/dj_narration.wav >> $LOG 2>&1

ls /tmp/dj_narration.wav/audio_*.wav 2>/dev/null | sort | \
  awk '{print "file '"'"'" $0 "'"'"'"}' > /tmp/dj_chunks.txt
/opt/homebrew/bin/ffmpeg -y -f concat -safe 0 -i /tmp/dj_chunks.txt \
  -c:a libmp3lame -q:a 4 /tmp/dj_narration.mp3 >> $LOG 2>&1
echo "$(date): TTS → /tmp/dj_narration.mp3" >> $LOG

echo "request_queue.push /tmp/dj_narration.mp3" | nc localhost 1234 2>/dev/null || true
echo "request_queue.push /tmp/dj_next.mp3" | nc localhost 1234 2>/dev/null || true
echo "$(date): Done" >> $LOG
