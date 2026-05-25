#!/usr/bin/env python3
"""
run.py — YouTube Horror Channel Automation Pipeline

Usage:
    python run.py                                    # Random topic, full pipeline
    python run.py --topic "security guard camera"    # Custom topic
    python run.py --no-upload                        # Generate only, skip YouTube
    python run.py --shorts                           # 9:16 Shorts format
    python run.py --topic "my topic" --keep-temp     # Debug: keep intermediate files

Pipeline:
    1.  Generate horror script         (Gemini)
    2.  TTS narration                  (edge-tts, ChristopherNeural -5%)
    3.  Fetch stock footage            (Pexels API or gradient fallback)
    4.  Get ambient music              (CC0 download or synthesized drone)
    5.  Mix audio                      (narration 100% + music 17%)
    6.  Generate captions              (Whisper base model)
    7.  Compose video                  (ffmpeg + dark grade + grain + vignette)
    8.  Generate SEO metadata          (Gemini)
    9.  Generate thumbnail             (Pillow + Pexels or dark fallback)
    10. Upload to YouTube              (OAuth 2.0, public, AI disclosure set)

Output files (in --out-dir):
    output.mp4       Final video
    thumbnail.jpg    Custom thumbnail
    metadata.json    Title, description, tags, YouTube response
"""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _size_mb(p: Path) -> str:
    return f"{p.stat().st_size / 1024 / 1024:.1f} MB"


def main():
    ap = argparse.ArgumentParser(description="YouTube Horror Video Automation")
    ap.add_argument("--topic", default=None,
                    help="Story premise (optional — picks from curated list if omitted)")
    ap.add_argument("--shorts", action="store_true",
                    help="Produce 9:16 vertical Shorts instead of 16:9 long-form")
    ap.add_argument("--no-upload", action="store_true",
                    help="Skip YouTube upload (generate files only)")
    ap.add_argument("--out-dir", default=".", metavar="DIR",
                    help="Output directory for final files (default: current dir)")
    ap.add_argument("--keep-temp", action="store_true",
                    help="Keep temp working directory for debugging")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="ytauto-"))

    print("=" * 62)
    print("  YouTube Horror Channel — Automation Pipeline")
    print("=" * 62)

    try:
        # ── 1. Script ──────────────────────────────────────────────
        print("\n[1/10] Generating horror script via Gemini...")
        from pipeline.content import gen_horror_script
        content = gen_horror_script(args.topic, shorts=args.shorts)
        print(f"       Topic : {content['topic']}")
        if args.shorts:
            print(f"       Words : {content['word_count']} (~{content['word_count'] * 60 // 150}s at -5% rate)")
        else:
            print(f"       Words : {content['word_count']} (~{content['word_count']//150} min)")
        print(f"       Hook  : {content['hook'][:90]}...")
        (tmp / "script.txt").write_text(content["script"], encoding="utf-8")

        # ── 2. TTS ────────────────────────────────────────────────
        print("\n[2/10] Generating TTS narration (ChristopherNeural, -5% rate)...")
        from pipeline.tts import generate_narration
        narration = generate_narration(content["script"], tmp / "narration.mp3")
        print(f"       Narration ready")

        # ── 3. Stock footage ──────────────────────────────────────
        print("\n[3/10] Fetching dark cinematic stock footage (Pexels)...")
        from pipeline.visuals import fetch_horror_footage
        footage = fetch_horror_footage(tmp_dir=tmp, count=6)

        # ── 4. Ambient music ──────────────────────────────────────
        print("\n[4/10] Getting horror ambient music...")
        from pipeline.audio import fetch_or_generate_ambient
        from pipeline.compose import get_duration
        dur = get_duration(narration)
        print(f"       Narration duration: {dur:.1f}s ({dur/60:.1f} min)")
        ambient = fetch_or_generate_ambient(dur, tmp)

        # ── 5. Mix audio ──────────────────────────────────────────
        print("\n[5/10] Mixing narration + ambient (17% music level)...")
        from pipeline.audio import mix_narration_and_music
        mixed = mix_narration_and_music(narration, ambient, tmp / "mixed.mp3",
                                        narration_duration=dur)

        # ── 6. Captions ───────────────────────────────────────────
        print("\n[6/10] Generating Whisper captions (first run downloads ~140MB model)...")
        from pipeline.captions import generate_captions
        srt = generate_captions(narration, tmp / "captions.srt")
        print("       Captions ready")

        # ── 7. Video composition ──────────────────────────────────
        print("\n[7/10] Composing video (dark grade + grain + vignette + captions)...")
        from pipeline.compose import compose_horror_video
        raw_video = tmp / "video.mp4"
        compose_horror_video(footage, mixed, srt, raw_video, shorts=args.shorts)
        print(f"       Video composed: {_size_mb(raw_video)}")

        # ── 8. SEO metadata ───────────────────────────────────────
        print("\n[8/10] Generating SEO title, description, tags via Gemini...")
        from pipeline.seo import generate_seo_metadata, generate_shorts_seo
        if args.shorts:
            metadata = generate_shorts_seo(content["topic"])
        else:
            metadata = generate_seo_metadata(content["script"], content["topic"])
        print(f"       Title : {metadata['title']}")
        print(f"       Tags  : {len(metadata.get('tags', []))} tags")

        # ── 9. Thumbnail ──────────────────────────────────────────
        print("\n[9/10] Generating horror thumbnail (Pillow)...")
        from pipeline.thumbnail import generate_thumbnail
        thumb = generate_thumbnail(metadata["title"], tmp / "thumbnail.jpg", tmp)
        print(f"       Thumbnail: {_size_mb(thumb)}")

        # ── Copy outputs ──────────────────────────────────────────
        final_video = out_dir / "output.mp4"
        final_thumb = out_dir / "thumbnail.jpg"
        final_meta = out_dir / "metadata.json"
        shutil.copy2(raw_video, final_video)
        shutil.copy2(thumb, final_thumb)
        final_meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        # ── 10. Upload ────────────────────────────────────────────
        if not args.no_upload:
            print("\n[10/10] Uploading to YouTube...")
            from pipeline.upload import upload_video
            url = upload_video(final_video, final_thumb, metadata)
            metadata["youtube_url"] = url
            final_meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

            print(f"\n{'='*62}")
            print(f"  LIVE: {url}")
            print(f"{'='*62}")
        else:
            print("\n[10/10] Upload skipped (--no-upload)")
            print(f"\n{'='*62}")
            print(f"  Files ready in: {out_dir.resolve()}")
            print(f"  Video    : {final_video.name}  ({_size_mb(final_video)})")
            print(f"  Thumbnail: {final_thumb.name}")
            print(f"  Metadata : {final_meta.name}")
            print(f"{'='*62}")

    finally:
        if args.keep_temp:
            print(f"\n  Temp dir: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
