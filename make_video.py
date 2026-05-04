#!/usr/bin/env python3
"""
make_video.py — Minimalist YouTube video generator.

Usage:
    python make_video.py --type reddit --text "Your story text here..." --out video.mp4
    python make_video.py --type reddit --reddit-url <url> --out video.mp4
    python make_video.py --type motivational --theme "discipline" --out video.mp4
    python make_video.py --type history --topic "Roman Empire fall" --out video.mp4

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
import json
import os
import re
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
    "narrator_f":  "en-US-AriaNeural",      # warm female (default)
    "narrator_m":  "en-US-GuyNeural",       # confident male
    "doc":         "en-US-JennyNeural",     # documentary
    "deep":        "en-US-DavisNeural",     # deep authoritative
    "british_f":   "en-GB-SoniaNeural",     # British female
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
    body  = post.get("selftext", "").strip()
    return f"{title}.\n\n{body}"


def gen_script_with_gemini(prompt: str) -> str:
    """Use Gemini free tier to draft a 200-300 word script."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("ERROR: set GEMINI_API_KEY env var (https://aistudio.google.com/app/apikey)")
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    sys_prompt = (
        "Write a 60-second YouTube script (~150 words). "
        "Hard rules: hook in first sentence (curiosity gap or shock). "
        "Short punchy sentences. No intros like 'Hey guys'. "
        "End with a thought-provoking line. Plain prose only, no stage directions."
    )
    resp = model.generate_content(f"{sys_prompt}\n\nTOPIC: {prompt}")
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
        return gen_script_with_gemini(f"A surprising historical mini-documentary about: {args.topic}")
    if args.type == "horror":
        if not args.theme:
            sys.exit("ERROR: --theme required for type=horror")
        return gen_script_with_gemini(f"A short, unsettling true-style horror story about {args.theme}. First-person. Eerie tone.")
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
    model = whisper.load_model("base")  # ~140MB; "tiny" is faster but less accurate
    result = model.transcribe(str(audio_path), word_timestamps=True, verbose=False)

    def fmt(t: float) -> str:
        h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    # Group words into ~3-word phrases for punchy on-screen captions
    lines = []
    idx = 1
    for seg in result["segments"]:
        words = seg.get("words") or []
        if not words:
            lines.append((idx, seg["start"], seg["end"], seg["text"].strip()))
            idx += 1
            continue
        chunk = []
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
# Step 4: Compose video with ffmpeg
# ---------------------------------------------------------------------------

def get_audio_duration(mp3: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(mp3),
    ]).decode().strip()
    return float(out)


def compose_video(audio: Path, srt: Path, out_mp4: Path, shorts: bool = True):
    """Compose: animated gradient bg + voiceover + burned subtitles."""
    duration = get_audio_duration(audio)
    if shorts:
        w, h = 1080, 1920
    else:
        w, h = 1920, 1080

    # Subtitle styling: bold, white with black outline, centered, big for Shorts
    fontsize = 64 if shorts else 36
    sub_style = (
        f"FontName=Helvetica,FontSize={fontsize},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,BorderStyle=1,Outline=4,Shadow=0,"
        f"Alignment=2,MarginV={int(h*0.15)},Bold=1"
    )

    # Animated gradient background as an lavfi source input (no inputs of its own).
    bg_lavfi = (
        f"gradients=size={w}x{h}:duration={duration}:speed=0.05:"
        f"c0=0x1a1a2e:c1=0x16213e:c2=0x0f3460:c3=0xe94560:n=3"
    )

    # Escape srt path for filter (commas/colons would break it; tempdirs are usually safe but be careful).
    srt_escaped = str(srt).replace(":", r"\:").replace(",", r"\,")

    filter_complex = (
        f"[0:v]format=yuv420p,subtitles={srt_escaped}:force_style='{sub_style}'[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", bg_lavfi,
        "-i", str(audio),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Generate a minimalist YouTube video.")
    p.add_argument("--type", required=True, choices=["reddit", "motivational", "history", "horror"])
    p.add_argument("--text", help="Use this text directly as the script (skips content source).")
    p.add_argument("--reddit-url", help="Reddit post URL (for --type reddit).")
    p.add_argument("--theme", help="Theme/keyword (for motivational/horror).")
    p.add_argument("--topic", help="Topic (for history).")
    p.add_argument("--voice", default=DEFAULT_VOICE, help="edge-tts voice name.")
    p.add_argument("--out", default="output.mp4", help="Output MP4 path.")
    p.add_argument("--longform", action="store_true", help="Horizontal 16:9 instead of vertical Shorts.")
    p.add_argument("--keep-temp", action="store_true", help="Don't delete intermediate files.")
    args = p.parse_args()

    workdir = Path(tempfile.mkdtemp(prefix="ytvid-"))
    print(f"[1/4] Working dir: {workdir}")

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
    print(f"\n✅ Done: {out}")
    print(f"   Size: {out.stat().st_size / 1024 / 1024:.1f} MB")

    if not args.keep_temp:
        shutil.rmtree(workdir)
    else:
        print(f"   Temp files kept: {workdir}")


if __name__ == "__main__":
    main()
