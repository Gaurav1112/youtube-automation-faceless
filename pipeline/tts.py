"""Text-to-speech narration via edge-tts.

Default: ChristopherNeural at -5% rate — deep, slow, authoritative.
Best for horror: the slight slowing increases perceived dread.

Note: en-US-DavisNeural was removed from Microsoft's service in 2025.
ChristopherNeural is the closest remaining deep male voice.
"""

import asyncio
from pathlib import Path

import edge_tts


VOICES = {
    "horror_deep":    "en-US-ChristopherNeural",  # Deep authoritative — best for horror
    "horror_british": "en-GB-RyanNeural",          # British eerie quality
    "horror_female":  "en-US-AriaNeural",          # Warm, unsettling when slowed
    "documentary":    "en-US-JennyNeural",         # Clean documentary feel
    "horror_alt":     "en-US-EricNeural",          # Alternative deep male
}

DEFAULT_VOICE = VOICES["horror_deep"]
DEFAULT_RATE = "-5%"  # Slower pace = more ominous delivery


async def _tts(text: str, voice: str, rate: str, out: Path):
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await comm.save(str(out))


def generate_narration(
    text: str,
    out_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> Path:
    """Generate TTS narration MP3 from script text."""
    asyncio.run(_tts(text, voice, rate, out_path))
    return out_path
