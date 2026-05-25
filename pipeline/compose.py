"""ffmpeg video composition with cinematic horror visual treatment.

Effects applied to every video:
- Dark cinematic color grade (crush blacks, desaturate slightly)
- Film grain (noise filter, type=temporal for realistic grain)
- Vignette (darkens edges, focuses attention center)
- Burned-in Impact captions via Pillow→PNG→colorkey→overlay
  (no libass / subtitles filter dependency)

With stock footage: clips are looped to fill duration, then filtered.
Without stock footage: dark purple/red animated gradient fallback.
"""

import re
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ── SRT helpers ──────────────────────────────────────────────────────────────

def _srt_time(ts: str) -> float:
    """'00:01:23,456' → seconds as float."""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _parse_srt(srt_path: Path) -> list[tuple[float, float, str]]:
    """Return list of (start_sec, end_sec, text) from an SRT file."""
    text = srt_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", text.strip())
    entries: list[tuple[float, float, str]] = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        # lines[0] = index, lines[1] = timestamps, lines[2+] = text
        try:
            start_str, end_str = lines[1].split(" --> ")
            start = _srt_time(start_str.strip())
            end = _srt_time(end_str.strip())
            caption = " ".join(lines[2:]).strip()
            if caption:
                entries.append((start, end, caption))
        except (ValueError, IndexError):
            continue
    return entries


# ── Caption PNG rendering ─────────────────────────────────────────────────────

def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load Impact at given size, fall back to default font."""
    for path in [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.truetype("impact.ttf", size)
    except (OSError, IOError):
        return ImageFont.load_default()


def _render_caption_frame(
    text: str, w: int, h: int, font_size: int, shorts: bool = False
) -> Image.Image:
    """Render white text with black outline on pure black background.

    Black background → colorkey removes it later, leaving only glyphs visible.
    For Shorts, captions are centered vertically (MrBeast style).
    """
    img = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _get_font(font_size)

    # Wrap long captions — narrower wrap for Shorts' slim vertical frame
    if shorts:
        max_chars = 15
    else:
        max_chars = max(12, w // (font_size // 2))
    lines = textwrap.wrap(text, width=max_chars) or [text]

    # Measure total height for placement
    line_height = font_size + 8
    total_h = len(lines) * line_height
    if shorts:
        # Center of screen for Shorts (50% vertically)
        anchor_v = int(h * 0.50)
    else:
        # Bottom-third for regular videos (82% down the frame)
        anchor_v = int(h * 0.82)
    y = anchor_v - total_h // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (w - lw) // 2

        # Black outline (draw text offset in 8 directions)
        outline = 3
        for dx in range(-outline, outline + 1):
            for dy in range(-outline, outline + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))

        # White text on top
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_height

    return img


def _build_caption_track(
    entries: list[tuple[float, float, str]],
    total_duration: float,
    tmp_dir: Path,
    w: int,
    h: int,
    shorts: bool = False,
) -> Path:
    """Build a caption video track using PNG frames + ffmpeg concat demuxer.

    The track is the same resolution as the main video; black = transparent
    (removed later via colorkey). Between captions the frame is all-black
    (fully transparent).
    """
    if shorts:
        font_size = 64
    else:
        font_size = 56 if h > 1080 else 44
    blank = Image.new("RGB", (w, h), (0, 0, 0))

    cap_dir = tmp_dir / "cap_frames"
    cap_dir.mkdir(exist_ok=True)

    concat_lines: list[str] = []
    prev_end = 0.0
    frame_idx = 0

    for start, end, text in entries:
        # Gap before this caption (blank frame)
        gap = round(start - prev_end, 3)
        if gap > 0.001:
            blank_path = cap_dir / f"blank_{frame_idx:04d}.png"
            blank.save(blank_path)
            concat_lines.append(f"file '{blank_path}'\nduration {gap:.3f}")
            frame_idx += 1

        # Caption frame
        cap_img = _render_caption_frame(text, w, h, font_size, shorts=shorts)
        cap_path = cap_dir / f"cap_{frame_idx:04d}.png"
        cap_img.save(cap_path)
        dur = round(end - start, 3)
        concat_lines.append(f"file '{cap_path}'\nduration {max(dur, 0.04):.3f}")
        frame_idx += 1

        prev_end = end

    # Trailing blank to reach total_duration
    tail = round(total_duration - prev_end, 3)
    if tail > 0.001:
        blank_path = cap_dir / f"blank_{frame_idx:04d}.png"
        blank.save(blank_path)
        concat_lines.append(f"file '{blank_path}'\nduration {tail:.3f}")
        # ffmpeg concat demuxer needs the last file listed once more (no duration)
        concat_lines.append(f"file '{blank_path}'")

    concat_list = tmp_dir / "cap_concat.txt"
    concat_list.write_text("\n".join(concat_lines) + "\n")

    cap_track = tmp_dir / "cap_track.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-vf", f"fps=10,scale={w}:{h}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(cap_track),
    ], check=True, capture_output=True)

    return cap_track


def _burn_captions(
    base_video: Path, srt: Path, out: Path, w: int, h: int, shorts: bool = False
) -> Path:
    """Overlay caption track onto base_video via colorkey → overlay."""
    entries = _parse_srt(srt)
    if not entries:
        # No captions — just copy base video to out
        subprocess.run(["ffmpeg", "-y", "-i", str(base_video),
                        "-c", "copy", str(out)], check=True, capture_output=True)
        return out

    duration = get_duration(base_video)
    tmp_dir = out.parent
    cap_track = _build_caption_track(entries, duration, tmp_dir, w, h, shorts=shorts)

    # colorkey: black (0x000000) → transparent, then overlay on base
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(base_video),
        "-i", str(cap_track),
        "-filter_complex",
        "[1:v]colorkey=color=black:similarity=0.2:blend=0.05[cap];"
        "[0:v][cap]overlay=shortest=1[vout]",
        "-map", "[vout]",
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out),
    ], check=True)
    return out


# ── Public API ───────────────────────────────────────────────────────────────

def get_duration(path: Path) -> float:
    """Get media duration in seconds via ffprobe."""
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]).decode().strip()
    return float(out)


def compose_horror_video(
    footage_clips: list[Path],
    audio: Path,
    srt: Path,
    out: Path,
    shorts: bool = False,
) -> Path:
    """Compose final horror video. Uses stock footage or gradient fallback."""
    duration = get_duration(audio)
    w, h = (1080, 1920) if shorts else (1920, 1080)

    base = out.with_suffix(".base.mp4")
    if footage_clips:
        _compose_with_footage(footage_clips, audio, base, w, h, duration)
    else:
        _compose_gradient(audio, base, w, h, duration)

    return _burn_captions(base, srt, out, w, h, shorts=shorts)


# ── Video assembly (no captions) ─────────────────────────────────────────────

def _visual_filter(w: int, h: int) -> str:
    """Color grade + grain + vignette filter chain (no caption step)."""
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        "curves="
        "r='0/0 0.12/0.05 0.75/0.66 1/0.88':"
        "g='0/0 0.12/0.04 0.75/0.63 1/0.84':"
        "b='0/0 0.18/0.08 0.75/0.58 1/0.80',"
        "noise=alls=7:allf=t+u,"
        "vignette=PI/3.5"
    )


def _compose_with_footage(
    clips: list[Path],
    audio: Path,
    out: Path,
    w: int,
    h: int,
    duration: float,
) -> Path:
    clip_duration = max(duration / len(clips), 12.0)

    inputs: list[str] = []
    for clip in clips:
        inputs += ["-stream_loop", "99", "-i", str(clip)]
    inputs += ["-i", str(audio)]

    audio_idx = len(clips)
    filter_parts: list[str] = []
    video_labels: list[str] = []

    vf = _visual_filter(w, h)
    for i in range(len(clips)):
        label = f"v{i}"
        filter_parts.append(
            f"[{i}:v]{vf},"
            f"trim=duration={clip_duration},setpts=PTS-STARTPTS"
            f"[{label}];"
        )
        video_labels.append(f"[{label}]")

    n = len(clips)
    filter_parts.append(
        f"{''.join(video_labels)}concat=n={n}:v=1:a=0,"
        f"trim=duration={duration},setpts=PTS-STARTPTS"
        "[vout];"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", "".join(filter_parts),
        "-map", "[vout]",
        "-map", f"{audio_idx}:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def _compose_gradient(
    audio: Path,
    out: Path,
    w: int,
    h: int,
    duration: float,
) -> Path:
    """Horror-themed animated gradient fallback — deep purples, dark reds."""
    bg = (
        f"gradients=size={w}x{h}:duration={duration}:speed=0.015:"
        "c0=0x0d0008:c1=0x1a0010:c2=0x0a0015:c3=0x1f0005:n=4"
    )

    filter_complex = (
        "[0:v]"
        "noise=alls=5:allf=t+u,"
        "vignette=PI/3"
        "[vout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", bg,
        "-i", str(audio),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out
