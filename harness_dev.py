#!/usr/bin/env python3
"""
harness_dev.py — Development harness: validates entire pipeline locally
without real API calls (except TTS, which needs no API key).

Tests:
  ✓ System deps (ffmpeg, ffprobe, Python 3.12+)
  ✓ All Python packages installed
  ✓ .env configuration (warns on missing optional keys)
  ✓ TTS generation (edge-tts, no key needed)
  ✓ Ambient music synthesis (ffmpeg, no key needed)
  ✓ Video composition — gradient fallback (no Pexels key needed)
  ✓ Caption generation (Whisper, downloads ~140MB model once)
  ✓ Thumbnail generation (Pillow, dark fallback without Pexels)

Usage:
  python harness_dev.py           # Full test (includes Whisper + ffmpeg)
  python harness_dev.py --quick   # Skip Whisper + video (fast, ~30s)
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
B = "\033[94m"
X = "\033[0m"
BOLD = "\033[1m"


def ok(msg):   print(f"  {G}✓{X}  {msg}")
def err(msg):  print(f"  {R}✗{X}  {msg}")
def warn(msg): print(f"  {Y}⚠{X}  {msg}")


def section(title: str):
    print(f"\n{BOLD}{B}── {title} {'─' * (50 - len(title))}{X}")


def check_system() -> int:
    section("System Dependencies")
    failures = 0

    if shutil.which("ffmpeg"):
        v = subprocess.check_output(["ffmpeg", "-version"]).decode().split("\n")[0]
        ok(f"ffmpeg:  {v[:55]}")
    else:
        err("ffmpeg not found — brew install ffmpeg")
        failures += 1

    if shutil.which("ffprobe"):
        ok("ffprobe found")
    else:
        err("ffprobe not found (usually ships with ffmpeg)")
        failures += 1

    vi = sys.version_info
    if vi >= (3, 12):
        ok(f"Python {vi.major}.{vi.minor}.{vi.micro}")
    else:
        warn(f"Python {vi.major}.{vi.minor} — 3.12+ recommended")

    return failures


def check_packages() -> int:
    section("Python Packages")
    failures = 0

    pkgs = [
        ("edge_tts",              "edge-tts"),
        ("whisper",               "openai-whisper"),
        ("google.genai",          "google-genai"),
        ("PIL",                   "Pillow"),
        ("praw",                  "praw"),
        ("requests",              "requests"),
        ("dotenv",                "python-dotenv"),
        ("googleapiclient",       "google-api-python-client"),
        ("google_auth_oauthlib",  "google-auth-oauthlib"),
        ("google.auth",           "google-auth"),
    ]

    for mod, pkg in pkgs:
        try:
            __import__(mod)
            ok(pkg)
        except ImportError:
            err(f"{pkg} missing — pip install {pkg}")
            failures += 1

    return failures


def check_env() -> int:
    section("Environment Variables (.env)")

    required = {
        "GEMINI_API_KEY":        "Script + SEO generation (required for full run)",
        "YOUTUBE_CLIENT_ID":     "YouTube upload OAuth (required for upload)",
        "YOUTUBE_CLIENT_SECRET": "YouTube upload OAuth (required for upload)",
    }
    optional = {
        "PEXELS_API_KEY":   "Stock footage + thumbnail backgrounds (highly recommended)",
        "REDDIT_CLIENT_ID": "Live Reddit post sourcing",
    }

    failures = 0
    for key, desc in required.items():
        val = os.environ.get(key, "")
        if val and "your_" not in val:
            ok(f"{key}")
        else:
            err(f"{key} not set — {desc}")
            failures += 1

    for key, desc in optional.items():
        val = os.environ.get(key, "")
        if val and "your_" not in val:
            ok(f"{key} (optional)")
        else:
            warn(f"{key} not set — {desc}")

    return failures


def check_tts() -> int:
    section("TTS Narration (edge-tts)")
    tmp = Path(tempfile.mkdtemp(prefix="harness-"))
    try:
        from pipeline.tts import generate_narration
        text = (
            "The shadows moved before I turned the light on. "
            "Something had been in my house. I could feel it."
        )
        out = tmp / "test.mp3"
        generate_narration(text, out)
        if out.exists() and out.stat().st_size > 8_000:
            ok(f"TTS OK — {out.stat().st_size // 1024} KB")
            return 0
        err("TTS output empty or too small")
        return 1
    except Exception as e:
        err(f"TTS failed: {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_ambient() -> int:
    section("Ambient Music Synthesis (ffmpeg)")
    tmp = Path(tempfile.mkdtemp(prefix="harness-"))
    try:
        from pipeline.audio import _synthesize_drone
        out = tmp / "ambient.mp3"
        _synthesize_drone(20.0, out)
        if out.exists() and out.stat().st_size > 5_000:
            ok(f"Ambient drone OK — {out.stat().st_size // 1024} KB")
            return 0
        err("Ambient output empty")
        return 1
    except Exception as e:
        err(f"Ambient synthesis failed: {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_video_pipeline() -> int:
    section("Full Video Pipeline (TTS → Whisper → ffmpeg compose)")
    tmp = Path(tempfile.mkdtemp(prefix="harness-"))
    failures = 0

    try:
        from pipeline.tts import generate_narration
        text = (
            "This is a pipeline test. The door was open when I came home. "
            "I never leave the door open. Something was wrong. I could feel it. "
            "The lights were off. I didn't turn them off."
        )
        narration = tmp / "narration.mp3"
        generate_narration(text, narration)
        ok("TTS narration generated")

        from pipeline.audio import fetch_or_generate_ambient, mix_narration_and_music
        from pipeline.compose import get_duration
        dur = get_duration(narration)
        ambient = fetch_or_generate_ambient(dur, tmp)
        mixed = mix_narration_and_music(narration, ambient, tmp / "mixed.mp3",
                                        narration_duration=dur)
        ok("Audio mixed")

        print("    Running Whisper (may download ~140MB model on first run)...")
        from pipeline.captions import generate_captions
        srt = generate_captions(narration, tmp / "test.srt")
        ok("Whisper captions generated")

        from pipeline.compose import compose_horror_video
        out_video = tmp / "test_video.mp4"
        compose_horror_video([], mixed, srt, out_video)

        if out_video.exists() and out_video.stat().st_size > 50_000:
            ok(f"Video composed OK — {out_video.stat().st_size // 1024} KB")
        else:
            err("Video output missing or too small")
            failures += 1

    except Exception as e:
        err(f"Pipeline failed: {e}")
        failures += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return failures


def check_thumbnail() -> int:
    section("Thumbnail Generation (Pillow)")
    tmp = Path(tempfile.mkdtemp(prefix="harness-"))
    try:
        from pipeline.thumbnail import generate_thumbnail
        out = tmp / "thumb.jpg"
        generate_thumbnail(
            "This Horror Story Destroyed My Sleep For 3 Weeks",
            out, tmp,
        )
        if out.exists() and out.stat().st_size > 30_000:
            ok(f"Thumbnail OK — {out.stat().st_size // 1024} KB")
            return 0
        err("Thumbnail missing or too small")
        return 1
    except Exception as e:
        err(f"Thumbnail failed: {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Dev harness — validate pipeline without upload")
    ap.add_argument("--quick", action="store_true",
                    help="Skip Whisper + video composition (fast ~30s check)")
    args = ap.parse_args()

    print(f"\n{BOLD}YouTube Automation — Dev Harness{X}")
    print("Validating pipeline components...\n")

    from dotenv import load_dotenv
    load_dotenv()

    total = 0
    total += check_system()
    total += check_packages()
    total += check_env()
    total += check_tts()

    if not args.quick:
        total += check_ambient()
        total += check_video_pipeline()
        total += check_thumbnail()
    else:
        total += check_ambient()
        total += check_thumbnail()

    section("Result")
    if total == 0:
        print(f"\n  {G}{BOLD}All checks passed. Pipeline is ready.{X}")
        print(f"\n  To generate a video without uploading:")
        print(f"    python run.py --no-upload")
        print(f"\n  To run the full pipeline (generate + upload):")
        print(f"    python run.py")
    else:
        print(f"\n  {R}{BOLD}{total} check(s) failed — fix above issues then re-run.{X}")
        sys.exit(1)
    print()


if __name__ == "__main__":
    main()
