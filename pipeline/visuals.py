"""Dark cinematic stock footage from Pexels API.

Fetches CC0 horror-appropriate clips: fog, abandoned places, dark forests.
Falls back gracefully when no API key is present.
"""

import os
import random
import subprocess
import time
from pathlib import Path

import requests


PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"

HORROR_QUERIES = [
    "dark forest fog night",
    "abandoned building interior dark",
    "fog mist night atmospheric",
    "dark corridor hallway",
    "storm lightning night dramatic",
    "empty road night dark",
    "dark lake mist fog",
    "shadow silhouette darkness",
    "old abandoned house",
    "dark clouds dramatic sky",
]


def fetch_horror_footage(tmp_dir: Path, count: int = 6) -> list[Path]:
    """Fetch dark atmospheric stock clips from Pexels.

    Returns list of local MP4 paths. Empty list if no API key (triggers gradient fallback).
    """
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        print("  [visuals] No PEXELS_API_KEY — will use cinematic gradient fallback")
        return []

    clips: list[Path] = []
    headers = {"Authorization": api_key}
    queries = random.sample(HORROR_QUERIES, min(count + 2, len(HORROR_QUERIES)))

    for i, query in enumerate(queries):
        if len(clips) >= count:
            break
        try:
            resp = requests.get(PEXELS_VIDEO_API, headers=headers, params={
                "query": query,
                "per_page": 5,
                "orientation": "landscape",
                "size": "large",
            }, timeout=20)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            if not videos:
                continue

            video = random.choice(videos[:3])
            hd_file = next(
                (f for f in video.get("video_files", [])
                 if f.get("quality") == "hd" and "mp4" in f.get("file_type", "")),
                next(
                    (f for f in video.get("video_files", []) if "mp4" in f.get("file_type", "")),
                    None
                ),
            )
            if not hd_file:
                continue

            out = tmp_dir / f"footage_{i:02d}.mp4"
            _download(hd_file["link"], out)
            clips.append(out)
            print(f"  [visuals] Clip {len(clips)}/{count}: {query}")
            time.sleep(0.3)

        except Exception as e:
            print(f"  [visuals] Clip {i} failed ({e!r}) — skipping")
            continue

    print(f"  [visuals] {len(clips)} clips ready")
    return clips


def loop_clip(clip: Path, duration: float, out: Path) -> Path:
    """Loop a short clip to fill the required duration."""
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "99",
        "-i", str(clip),
        "-t", str(duration),
        "-c", "copy",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def _download(url: str, dest: Path):
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(65536):
            f.write(chunk)
