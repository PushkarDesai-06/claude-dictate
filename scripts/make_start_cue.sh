#!/usr/bin/env bash
# Builds the "recording started" cue from the "recording stopped" one by flipping its
# pitch contour. The stop cue falls from a short E5 to a long A4. The start cue keeps
# that long A4 untouched and drops the short note an octave to E4, so it rises from
# E4 to A4: same notes, same register, same timbre, opposite direction.
set -euo pipefail

readonly SOUNDS_DIR="$(cd "$(dirname "$(readlink -f "$0")")/../assets/sounds" && pwd)"
readonly SOURCE="$SOUNDS_DIR/recording-stopped.mp3"
readonly OUTPUT="$SOUNDS_DIR/recording-started.mp3"

readonly SECOND_NOTE_ONSET=0.16
readonly SAMPLE_RATE=44100
readonly JOIN_FADE=0.008

calc() { awk "BEGIN { printf \"%.6f\", $1 }"; }

readonly FADE_START=$(calc "$SECOND_NOTE_ONSET - $JOIN_FADE")
readonly OCTAVE_DOWN_RATE=$((SAMPLE_RATE / 2))

# Halving the playback rate drops exactly one octave with no pitch-shift artifacts;
# atempo then restores the original length so the rhythm is unchanged.
ffmpeg -y -v error -i "$SOURCE" -filter_complex "
  [0:a]asplit=2[full][tail];
  [full]asetrate=$OCTAVE_DOWN_RATE,aresample=$SAMPLE_RATE,atempo=2.0,
        atrim=end=$SECOND_NOTE_ONSET,asetpts=PTS-STARTPTS,
        afade=t=out:st=$FADE_START:d=$JOIN_FADE[first];
  [tail]atrim=start=$SECOND_NOTE_ONSET,asetpts=PTS-STARTPTS,
        afade=t=in:d=0.002[second];
  [first][second]concat=n=2:v=0:a=1[out]
" -map "[out]" -c:a libmp3lame -b:a 256k "$OUTPUT"

echo "wrote $OUTPUT"
