#!/usr/bin/env python3
"""
harness_google.py — Validate YouTube API credentials and OAuth flow.

Tests:
  ✓ YOUTUBE_CLIENT_ID / CLIENT_SECRET present
  ✓ OAuth 2.0 flow (opens browser once for first-time auth)
  ✓ Channel info fetch (confirms credentials work)
  ✓ Upload quota reminder

Flags:
  --test-upload   Upload a 1-second private black video (uses quota: ~1600 units)
  --reset-auth    Delete cached OAuth token (forces re-authentication)

Usage:
  python harness_google.py              # Auth check
  python harness_google.py --test-upload
  python harness_google.py --reset-auth
"""

import argparse
import os
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


def check_credentials() -> int:
    section("YouTube API Credentials")
    failures = 0

    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
    secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")

    if client_id and "your_" not in client_id:
        ok(f"YOUTUBE_CLIENT_ID  ({client_id[:24]}...)")
    else:
        err("YOUTUBE_CLIENT_ID not set — see .env.example")
        failures += 1

    if secret and "your_" not in secret:
        ok("YOUTUBE_CLIENT_SECRET")
    else:
        err("YOUTUBE_CLIENT_SECRET not set — see .env.example")
        failures += 1

    return failures


def check_oauth_and_channel() -> int:
    section("OAuth 2.0 + Channel Verification")
    from pipeline.upload import TOKEN_FILE

    if TOKEN_FILE.exists():
        ok(f"Cached token: {TOKEN_FILE}")
    else:
        warn("No token yet — browser will open for one-time OAuth consent")

    try:
        from pipeline.upload import _build_client
        print("    Building client (may open browser)...")
        youtube = _build_client()
        ok("OAuth complete / token refreshed")

        resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        items = resp.get("items", [])
        if not items:
            err("No channel found for this Google account")
            return 1

        ch = items[0]
        name = ch["snippet"]["title"]
        subs = ch["statistics"].get("subscriberCount", "hidden")
        vids = ch["statistics"].get("videoCount", "0")
        ok(f"Channel: '{name}' — {subs} subs, {vids} videos")
        return 0

    except Exception as e:
        err(f"OAuth/channel check failed: {e}")
        return 1


def check_quota() -> int:
    section("Upload Quota")
    warn("Quota: 10,000 units/day. Each upload costs ~1,600 units (~6 uploads/day free).")
    warn("Check remaining: https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas")
    ok("Reminder logged (quota not fetchable via API)")
    return 0


def test_upload() -> int:
    section("Test Upload (1-second private video)")
    tmp = Path(tempfile.mkdtemp(prefix="harness-upload-"))
    try:
        test_video = tmp / "test.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:size=1920x1080:duration=1",
            "-f", "lavfi", "-i", "aevalsrc=0:s=44100:duration=1",
            "-c:v", "libx264", "-c:a", "aac",
            str(test_video),
        ], check=True, capture_output=True)

        from pipeline.upload import _build_client
        import googleapiclient.http
        youtube = _build_client()

        body = {
            "snippet": {
                "title": "[HARNESS TEST] Delete Me",
                "description": "Automated test — safe to delete",
                "tags": ["test"],
                "categoryId": "22",
            },
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
        }
        req = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=googleapiclient.http.MediaFileUpload(str(test_video), resumable=True),
        )
        _, response = req.next_chunk()
        if response and "id" in response:
            vid = response["id"]
            ok(f"Test video uploaded (private): https://youtu.be/{vid}")
            warn("Delete this test video from YouTube Studio when done")
        else:
            warn("Upload returned no ID — check YouTube Studio manually")
        return 0

    except Exception as e:
        err(f"Test upload failed: {e}")
        return 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def reset_auth():
    from pipeline.upload import TOKEN_FILE
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"  Token deleted: {TOKEN_FILE}")
    else:
        print("  No token file found")


def main():
    ap = argparse.ArgumentParser(description="Validate YouTube API credentials")
    ap.add_argument("--test-upload", action="store_true",
                    help="Upload a 1-second private test video (uses ~1600 quota units)")
    ap.add_argument("--reset-auth", action="store_true",
                    help="Delete cached OAuth token")
    args = ap.parse_args()

    print(f"\n{BOLD}YouTube Automation — Google Harness{X}")

    from dotenv import load_dotenv
    load_dotenv()

    if args.reset_auth:
        reset_auth()
        return

    total = 0
    total += check_credentials()
    total += check_oauth_and_channel()
    total += check_quota()

    if args.test_upload:
        total += test_upload()

    section("Result")
    if total == 0:
        print(f"\n  {G}{BOLD}Google harness passed. YouTube upload is ready.{X}")
        print(f"\n  Run the full pipeline:")
        print(f"    python run.py")
    else:
        print(f"\n  {R}{BOLD}{total} check(s) failed.{X}")
        sys.exit(1)
    print()


if __name__ == "__main__":
    main()
