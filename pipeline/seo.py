"""SEO metadata generation for YouTube via Gemini.

Uses competitor-analyzed title formulas from top horror channels.
Targets long-tail keywords with low competition for new channels.
"""

import json
import os
import sys


SEO_PROMPT = """\
You are a YouTube SEO expert for horror/NoSleep channels. Generate metadata that maximizes CTR
and discoverability on YouTube for a new channel.

Return ONLY valid JSON with these exact keys (no markdown, no explanation):
{
  "title": "max 60 chars — curiosity gap title. Must contain 'horror' or 'scary' or 'NoSleep' or 'true story'.",
  "description": "450-500 word description. First 2 sentences are the hook (show before 'more'). Include: 6 natural keyword mentions, timestamps placeholder (0:00 Story Begins, etc.), CTA ('subscribe for more'), 10 hashtags at end.",
  "tags": ["exactly 15 tags — mix broad + long-tail. Must include: nosleep, horror stories, scary stories, true horror, horror narration, reddit horror, creepypasta, scary reddit stories, paranormal, horror 2026"],
  "category_id": "22",
  "publish_at": null
}

Proven title formulas for horror channels (use the best fit):
1. "This [Reddit/NoSleep] Story [Strong Emotion] Me For [Time Period]"
2. "The Most Disturbing [Story Type] I've Ever [Read/Found/Heard]"
3. "True Horror: [Intriguing Premise That Creates Dread]"
4. "[Number] Horror Stories From Reddit That Will Keep You Up Tonight"
5. "I [Action] For [Duration] And What I Found Still Haunts Me"
6. "This Story Was Deleted From Reddit Hours After Posting [And Here's Why]"
"""


SHORTS_SEO_PROMPT = """\
You are a YouTube Shorts SEO expert for horror channels. Generate metadata that gets the Shorts recommended.

Return ONLY valid JSON (no markdown):
{
  "title": "max 55 chars — must include #Shorts at the end. Horror hook formula: '[Disturbing premise] #Shorts'",
  "description": "3 lines max. Line 1: story hook (1 sentence). Line 2: empty. Line 3: '#Shorts #horror #scarystories #nosleep #horrortok #scarytok #creepypasta #paranormal #horrorfyp #truehorror'",
  "tags": ["exactly 10 tags: shorts, horror shorts, scary shorts, horror stories shorts, nosleep shorts, scary tiktok, horror fyp, true horror story, creepypasta shorts, paranormal shorts"],
  "category_id": "22",
  "publish_at": null
}

Title formulas that work for horror Shorts:
1. "[Impossible thing that happened] #Shorts"
2. "This [entity] has been [doing thing] for [duration] #Shorts"
3. "[First-person revelation of horror] #Shorts"
"""


def generate_shorts_seo(topic: str) -> dict:
    """Generate YouTube Shorts-optimized title, description, and tags."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: GEMINI_API_KEY not set")

    import google.genai as genai
    client = genai.Client(api_key=api_key)

    prompt = f"{SHORTS_SEO_PROMPT}\n\nSTORY TOPIC: {topic}"
    resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    raw = resp.text.strip()

    # Strip markdown code fences if present
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _fallback_shorts_metadata(topic)


def _fallback_shorts_metadata(topic: str) -> dict:
    return {
        "title": f"This Horror Story Is Terrifying #Shorts",
        "description": (
            f"{topic}\n\n"
            "#Shorts #horror #scarystories #nosleep #horrortok "
            "#scarytok #creepypasta #paranormal #horrorfyp #truehorror"
        ),
        "tags": [
            "shorts", "horror shorts", "scary shorts", "horror stories shorts",
            "nosleep shorts", "scary tiktok", "horror fyp", "true horror story",
            "creepypasta shorts", "paranormal shorts",
        ],
        "category_id": "22",
        "publish_at": None,
    }


def generate_seo_metadata(script: str, topic: str) -> dict:
    """Generate YouTube-optimized title, description, and tags."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: GEMINI_API_KEY not set")

    import google.genai as genai
    client = genai.Client(api_key=api_key)

    prompt = f"{SEO_PROMPT}\n\nSTORY TOPIC: {topic}\nSCRIPT EXCERPT:\n{script[:1800]}"
    resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    raw = resp.text.strip()

    # Strip markdown code fences if present
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _fallback_metadata(topic)


def _fallback_metadata(topic: str) -> dict:
    return {
        "title": "True Horror Story That Will Keep You Up Tonight",
        "description": (
            f"A terrifying true horror story: {topic}\n\n"
            "This horror narration will haunt you long after it ends. "
            "True scary stories from the darkest corners of the internet.\n\n"
            "0:00 Story Begins\n\n"
            "Subscribe for weekly horror narrations.\n\n"
            "#horror #nosleep #scarystories #truehorrory #horrornarration "
            "#reddit #creepypasta #paranormal #scaryreddit #horrorstories"
        ),
        "tags": [
            "nosleep", "horror stories", "scary stories", "true horror",
            "horror narration", "reddit horror", "creepypasta", "paranormal",
            "scary reddit stories", "horror 2026", "true scary stories",
            "nosleep reddit", "horror story", "reddit scary", "disturbing stories",
        ],
        "category_id": "22",
        "publish_at": None,
    }
