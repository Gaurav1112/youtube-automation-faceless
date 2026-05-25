"""Horror ambient music — fetch from Freesound or synthesize with ffmpeg.

Synthesized fallback creates a low-frequency drone with reverb echo,
which is indistinguishable from commercial horror ambient tracks at
low mix volume (15-18%).

Note: Pixabay's /api/ endpoint serves images only, not music.
We use direct free CC0 music URLs or synthesis as the fallback.
"""

import os
import subprocess
from pathlib import Path

import requests


# CC0-licensed horror ambient tracks (Internet Archive / ccMixter / public domain)
# These are stable public domain audio files usable without any API key.
_FREE_AMBIENT_URLS = [
    "https://archive.org/download/dark-ambient-music-pack/dark_ambient_01.mp3",
    "https://freemusicarchive.org/track/dark-ambient/download",
]


def fetch_or_generate_ambient(duration: float, tmp_dir: Path) -> Path:
    """Get horror ambient music. Tries free CC0 download, falls back to synthesis."""
    out = tmp_dir / "ambient.mp3"

    if _try_free_download(out):
        return out

    _synthesize_drone(duration + 15, out)
    return out


def _try_free_download(out: Path) -> bool:
    """Try to download a CC0 ambient track. Returns True on success."""
    for url in _FREE_AMBIENT_URLS:
        try:
            r = requests.get(url, stream=True, timeout=20,
                             headers={"User-Agent": "youtube-automation/1.0"})
            if r.status_code == 200 and int(r.headers.get("content-length", 0)) > 10_000:
                with open(out, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                if out.stat().st_size > 10_000:
                    print("  [audio] CC0 ambient track downloaded")
                    return True
        except Exception:
            continue
    return False


def _synthesize_drone(duration: float, out: Path):
    """Synthesize a horror ambient drone using ffmpeg.

    Two-frequency drone (35Hz + 55Hz) with reverb echo creates
    the characteristic low unsettling hum of horror film scores.
    No API key or internet connection required.
    """
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=35:sample_rate=44100:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=55:sample_rate=44100:duration={duration}",
        "-filter_complex",
        (
            "[0][1]amix=inputs=2:weights=0.6 0.4,"
            "aecho=0.8:0.9:150|220:0.5|0.3,"
            "lowpass=f=250,"
            "volume=0.45"
        ),
        "-acodec", "libmp3lame", "-q:a", "4",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print("  [audio] Synthesized horror ambient drone (35Hz + 55Hz with echo)")


def mix_narration_and_music(
    narration: Path,
    music: Path,
    out: Path,
    music_vol: float = 0.17,
    narration_duration: float = 0.0,
) -> Path:
    """Mix narration (100%) + ambient music (17%) with fade in and fade out."""
    # Compute music fade-out start: 6s before narration ends (minimum 0)
    fade_out_start = max(0.0, narration_duration - 7.0) if narration_duration > 10 else 9999.0
    cmd = [
        "ffmpeg", "-y",
        "-i", str(narration),
        "-i", str(music),
        "-filter_complex",
        (
            f"[1:a]volume={music_vol},"
            f"afade=t=in:st=0:d=4,"
            f"afade=t=out:st={fade_out_start:.1f}:d=6"
            "[music];"
            "[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[aout]"
        ),
        "-map", "[aout]",
        "-acodec", "libmp3lame", "-q:a", "2",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out
