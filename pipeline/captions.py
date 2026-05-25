"""Word-level caption generation using Whisper.

Groups words into 3-word chunks — matches the punchy subtitle style
used by top horror narration channels (Mr. Nightmare, etc.).
"""

from pathlib import Path


def _fmt(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def generate_captions(audio_path: Path, srt_path: Path) -> Path:
    """Transcribe audio with Whisper and write word-chunked SRT captions."""
    import whisper
    model = whisper.load_model("base")
    result = model.transcribe(str(audio_path), word_timestamps=True, verbose=False)

    lines: list[tuple] = []
    idx = 1

    for seg in result["segments"]:
        words = seg.get("words") or []
        if not words:
            lines.append((idx, seg["start"], seg["end"], seg["text"].strip()))
            idx += 1
            continue
        chunk: list = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= 3:
                lines.append((idx, chunk[0]["start"], chunk[-1]["end"],
                               " ".join(x["word"].strip() for x in chunk)))
                idx += 1
                chunk = []
        if chunk:
            lines.append((idx, chunk[0]["start"], chunk[-1]["end"],
                           " ".join(x["word"].strip() for x in chunk)))
            idx += 1

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, st, en, txt in lines:
            f.write(f"{i}\n{_fmt(st)} --> {_fmt(en)}\n{txt.upper()}\n\n")

    return srt_path
