import os
import re
from pathlib import Path

from anthropic import Anthropic

# Load prompts once at import
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _parse_code_blocks(response: str) -> tuple[str, str, str]:
    """Extract (german_title, sentence_match_markdown, tts_text) from Claude response."""
    # Match ```lang\ncontent``` - capture lang and content
    pattern = re.compile(r"```(\w+)\s*\n(.*?)```", re.DOTALL)
    blocks = pattern.findall(response)
    title = ""
    sentence_match = ""
    tts = ""
    # First ```text``` = title, first ```markdown``` = sentence match, second ```text``` = tts
    text_blocks = []
    for lang, content in blocks:
        content = content.strip()
        if lang == "text":
            text_blocks.append(content)
        elif lang == "markdown":
            sentence_match = content
    if len(text_blocks) >= 1:
        title = text_blocks[0]
    if len(text_blocks) >= 2:
        tts = text_blocks[1]
    return title, sentence_match, tts


def translate_transcript(
    transcript_text: str,
    video_title: str,
) -> tuple[str, str, str]:
    """
    Call Claude to produce German title, sentence-match script, and TTS script.
    Returns (translated_title, sentence_match_markdown, tts_text).
    """
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set")

    system = _load_prompt("translation_system.txt")
    examples = _load_prompt("german_style_examples.txt")
    if examples:
        system += "\n\n---\n\nGerman style examples:\n\n" + examples

    user = f"""VIDEO TITLE:
{video_title}

TRANSCRIPT (may be in any language):
{transcript_text}

Generate the German title, OUTPUT 1 (sentence-match: English + German), and OUTPUT 2 (German TTS script) as specified. If the transcript is not in English, translate it to English for the sentence match and to German for both columns. Output ONLY the three code blocks, nothing else."""

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = message.content[0].text if message.content else ""
    return _parse_code_blocks(text)
