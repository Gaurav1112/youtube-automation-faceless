"""Horror script generation using Gemini API.

Produces NoSleep-style stories optimized for YouTube retention:
3-act structure, curiosity-gap hooks, pattern interrupts, twist ending.
"""

import os
import re
import random
import sys
from pathlib import Path


HORROR_SYSTEM_PROMPT = """\
You are a master NoSleep horror storyteller writing for YouTube narration.

MANDATORY 3-ACT STRUCTURE:
ACT 1 — HOOK + SETUP (first 15% of words):
  - First sentence: one shocking/dread-inducing line. Start with revelation or action.
    GOOD: "The thing in my basement has been leaving me notes for three weeks."
    GOOD: "My daughter came home from school. My daughter died six years ago."
    BAD:  "It was a dark and stormy night..."  ← never use this
  - Establish character, location, normalcy. Plant one detail that feels wrong.

ACT 2 — ESCALATION (middle 60%):
  - First incident: something impossible happens.
  - Attempt to rationalize. Fails.
  - Pattern interrupt at ~35% mark: sudden revelation that reframes what we know.
  - Escalation: incidents get worse, closer, more personal.
  - Open loop before Act 3: "That's when I noticed something I should have seen from the beginning."

ACT 3 — CONFRONTATION + TWIST (final 25%):
  - The horror becomes undeniable and immediate.
  - Twist ending: a single revelation that changes the meaning of the entire story.
  - Closing line: haunting, unresolved. Should make viewer lie awake thinking.
    GOOD: "I checked the security footage from that night. The timestamp says 3:17 AM.
           My phone records show I called for help at 3:09 AM. I've been trying to
           figure out what happened in those eight minutes ever since."

CRAFT RULES:
- First-person narrator always (maximizes viewer identification)
- 1,450–1,600 words (hits 8–9 minutes at natural narration pace)
- Vary sentence rhythm: short punchy sentences for tension, longer flowing ones for dread
- FORBIDDEN phrases: "Little did I know", "spine-tingling", "blood-curdling", "heart pounding",
  "I'll never forget", "without warning", "out of nowhere", "needless to say"
- Frame as true: use "This happened last March", "I still check for it", "I moved out 3 weeks later"
- Include EXACTLY 2 pattern interrupts (mid-story revelations that reframe the narrative)
- The reader must feel dread, not just surprise

OUTPUT: Return ONLY the story text. No title. No headers. No stage directions. No author notes.\
"""

SHORTS_HORROR_PROMPT = """\
You are a master horror writer for YouTube Shorts.

Write EXACTLY 140-160 words. No more. Count every word.

MANDATORY STRUCTURE:
- Word 1-20: ONE sentence that is immediately disturbing. Something impossible happened. Start with the revelation.
  EXAMPLE: "My dead sister texted me at 3 AM. The message said: stop looking for me."
- Word 21-120: Build dread with short punchy sentences. 1 pattern interrupt that reframes everything. No filler words. No 'I walked' or 'I looked' sentences — show don't tell.
- Word 121-160: Single twist ending. One revelation that changes the meaning of everything before it. Close on an unresolved, haunting line.

FORBIDDEN: "Little did I know", "spine-tingling", "blood-curdling", "suddenly", "out of nowhere", "needless to say", any sentence longer than 15 words.

OUTPUT: Story text ONLY. No title. No word count. No headers.\
"""

HORROR_TOPICS = [
    "A night-shift security guard notices one camera feed is always 8 minutes behind",
    "A woman finds her own obituary dated two weeks from now, already framed on her wall",
    "A man receives voicemails from his own number, each one shorter and more desperate",
    "Someone's reflection starts moving a fraction of a second too late",
    "A new tenant discovers the apartment walls have doors that weren't on the floor plan",
    "A deep-sea researcher pulls up a recording device that went missing in 1987",
    "A hotel housekeeper finds the same handwritten note in every room: 'Don't look up'",
    "A woman notices her childhood home on Zillow — listed with photos from right now",
    "A man's GPS keeps rerouting him to the same abandoned house, no matter where he's going",
    "A sleep study participant realizes the scientists watching them have been replaced",
    "A park ranger's trail camera captures the same figure standing motionless — for 11 months",
    "A man discovers his neighbor has been dead for 6 months, but he spoke to her yesterday",
]

SEO_KEYWORDS = [
    "nosleep reddit horror",
    "true scary stories",
    "horror stories with twist ending",
    "real paranormal experiences",
    "creepypasta true story",
    "horror narration youtube",
    "disturbing true story",
    "scary stories reddit 2025",
    "horror stories that will haunt you",
    "r/nosleep best stories",
]


def gen_horror_script(topic: str | None = None, shorts: bool = False) -> dict:
    """Generate a horror script optimized for viral YouTube performance.

    Args:
        topic: Story premise. If None, picks from curated list.
        shorts: When True, generates a 140-160 word Shorts-optimized script.

    Returns dict with keys: topic, script, hook, word_count, keywords, shorts.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: GEMINI_API_KEY not set — get one free at https://aistudio.google.com/app/apikey")

    if not topic:
        topic = random.choice(HORROR_TOPICS)

    import google.genai as genai
    client = genai.Client(api_key=api_key)

    if shorts:
        prompt = f"{SHORTS_HORROR_PROMPT}\n\nWRITE A STORY ABOUT: {topic}"
    else:
        prompt = f"{HORROR_SYSTEM_PROMPT}\n\nWRITE A STORY ABOUT: {topic}"

    resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    script = resp.text.strip()

    # Extract first sentence as hook
    hook = re.split(r'(?<=[.!?])\s', script)[0]

    return {
        "topic": topic,
        "script": script,
        "hook": hook,
        "word_count": len(script.split()),
        "keywords": SEO_KEYWORDS,
        "shorts": shorts,
    }
