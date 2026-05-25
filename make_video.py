#!/usr/bin/env python3
"""
make_video.py — Minimalist YouTube video generator.

Usage:
    python make_video.py --type reddit --text "Your story text here..." --out video.mp4
    python make_video.py --type reddit --reddit-url <url> --out video.mp4
    python make_video.py --type motivational --theme "discipline" --out video.mp4
    python make_video.py --type history --topic "Roman Empire fall" --out video.mp4
    python make_video.py --type horror --theme "night shift" --out video.mp4

Format options:
    --shorts        9:16 vertical, max 60s (default)
    --longform      16:9 horizontal, no length cap

Pipeline:
    1. Get/generate script text (Reddit scrape | Gemini | direct text)
    2. edge-tts -> narration.mp3
    3. Whisper -> word-level captions (SRT)
    4. ffmpeg -> animated gradient bg + voice + burned-in captions -> MP4
"""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VOICES = {
    "narrator_f":  "en-US-AriaNeural",        # warm female (default)
    "narrator_m":  "en-US-GuyNeural",         # confident male
    "doc":         "en-US-JennyNeural",        # documentary
    "deep":        "en-US-ChristopherNeural",  # deep authoritative (was DavisNeural, removed 2025)
    "british_f":   "en-GB-SoniaNeural",        # British female
}

DEFAULT_VOICE = VOICES["narrator_f"]


# ---------------------------------------------------------------------------
# Step 1: Content sources
# ---------------------------------------------------------------------------

def get_reddit_text(url: str) -> str:
    """Fetch a Reddit post body using the public .json endpoint (no auth)."""
    import requests
    if not url.endswith(".json"):
        url = url.rstrip("/") + ".json"
    headers = {"User-Agent": "yt-channel/0.1 (script)"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    post = data[0]["data"]["children"][0]["data"]
    title = post.get("title", "").strip()
    body = post.get("selftext", "").strip()
    return f"{title}.\n\n{body}"


def gen_script_with_gemini(prompt: str) -> str:
    """Use Gemini to draft a 200-300 word script."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("ERROR: set GEMINI_API_KEY env var (https://aistudio.google.com/app/apikey)")
    import google.genai as genai
    client = genai.Client(api_key=api_key)
    sys_prompt = (
        "Write a 60-second YouTube script (~150 words). "
        "Hard rules: hook in first sentence (curiosity gap or shock). "
        "Short punchy sentences. No intros like 'Hey guys'. "
        "End with a thought-provoking line. Plain prose only, no stage directions."
    )
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"{sys_prompt}\n\nTOPIC: {prompt}",
    )
    return resp.text.strip()


def script_for_format(args) -> str:
    if args.text:
        return args.text
    if args.type == "reddit":
        if not args.reddit_url:
            sys.exit("ERROR: --reddit-url required for type=reddit (or use --text)")
        return get_reddit_text(args.reddit_url)
    if args.type == "motivational":
        if not args.theme:
            sys.exit("ERROR: --theme required for type=motivational")
        return gen_script_with_gemini(f"Motivational speech about {args.theme}.")
    if args.type == "history":
        if not args.topic:
            sys.exit("ERROR: --topic required for type=history")
        return gen_script_with_gemini(
            f"A surprising historical mini-documentary about: {args.topic}"
        )
    if args.type == "horror":
        if not args.theme:
            sys.exit("ERROR: --theme required for type=horror")
        return gen_script_with_gemini(
            f"A short, unsettling true-style horror story about {args.theme}. "
            "First-person. Eerie tone."
        )
    sys.exit(f"Unknown --type: {args.type}")


# ---------------------------------------------------------------------------
# Step 2: TTS
# ---------------------------------------------------------------------------

async def _tts_async(text: str, voice: str, out_mp3: Path):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="+0%")
    await communicate.save(str(out_mp3))


def tts_to_mp3(text: str, voice: str, out_mp3: Path):
    asyncio.run(_tts_async(text, voice, out_mp3))


# ---------------------------------------------------------------------------
# Step 3: Captions (Whisper)
# ---------------------------------------------------------------------------

def make_srt(audio_path: Path, srt_path: Path):
    import whisper
    model = whisper.load_model("base")
    result = model.transcribe(str(audio_path), word_timestamps=True, verbose=False)

    def fmt(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    lines = []
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
            f.write(f"{i}\n{fmt(st)} --> {fmt(en)}\n{txt.upper()}\n\n")


# ---------------------------------------------------------------------------
# Step 4: Compose video
# ---------------------------------------------------------------------------

def get_audio_duration(mp3: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(mp3),
    ]).decode().strip()
    return float(out)


def compose_video(audio: Path, srt: Path, out_mp4: Path, shorts: bool = True):
    """Compose: animated gradient bg + voiceover + Pillow-burned captions."""
    from pipeline.compose import _compose_gradient, _burn_captions
    duration = get_audio_duration(audio)
    w, h = (1080, 1920) if shorts else (1920, 1080)

    base = out_mp4.with_suffix(".base.mp4")
    _compose_gradient(audio, base, w, h, duration)
    _burn_captions(base, srt, out_mp4, w, h)
    base.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Generate a minimalist YouTube video.")
    p.add_argument("--type", required=True,
                   choices=["reddit", "motivational", "history", "horror"])
    p.add_argument("--text",
                   help="Use this text directly as the script (skips content source).")
    p.add_argument("--reddit-url", help="Reddit post URL (for --type reddit).")
    p.add_argument("--theme", help="Theme/keyword (for motivational/horror).")
    p.add_argument("--topic", help="Topic (for history).")
    p.add_argument("--voice", default=DEFAULT_VOICE, help="edge-tts voice name.")
    p.add_argument("--out", default="output.mp4", help="Output MP4 path.")
    p.add_argument("--longform", action="store_true",
                   help="Horizontal 16:9 instead of vertical Shorts.")
    p.add_argument("--keep-temp", action="store_true",
                   help="Don't delete intermediate files.")
    args = p.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    workdir = Path(tempfile.mkdtemp(prefix="ytvid-"))

    print("[1/4] Building script...")
    script_text = script_for_format(args)
    (workdir / "script.txt").write_text(script_text, encoding="utf-8")
    print(f"      Script length: {len(script_text)} chars")
    print(f"      Preview: {script_text[:120]}...")

    print("[2/4] TTS narration via edge-tts...")
    audio = workdir / "narration.mp3"
    tts_to_mp3(script_text, args.voice, audio)
    dur = get_audio_duration(audio)
    print(f"      Audio duration: {dur:.1f}s")

    print("[3/4] Generating captions via Whisper (this takes ~30-60s)...")
    srt = workdir / "captions.srt"
    make_srt(audio, srt)

    print("[4/4] Composing video with ffmpeg...")
    out = Path(args.out).resolve()
    compose_video(audio, srt, out, shorts=not args.longform)
    print(f"\nDone: {out}")
    print(f"   Size: {out.stat().st_size / 1024 / 1024:.1f} MB")

    if not args.keep_temp:
        shutil.rmtree(workdir)
    else:
        print(f"   Temp files kept: {workdir}")


if __name__ == "__main__":
    main()
