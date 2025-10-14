# src/llm/prompts.py
# Prompts for panel summaries, paragraph summaries, and novel mode.

SYSTEM_TEXT = """You are a careful assistant. Summarize the panel using ONLY the provided bubbles.
Do not invent names, places, or events. Keep it concise."""

USER_TEXT_TEMPLATE = """BUBBLES (JSON):
{payload}

Return JSON like:
{{
  "panel_summary": "one or two sentences.",
  "ordered_bubbles": [...]
}}
"""

SYSTEM_VLM = """You are a careful assistant. Summarize the panel using ONLY the provided text list.
Do not invent names, places, or events. Be concise."""

USER_VLM_TEMPLATE = """BUBBLES (ordered lines):
{joined}

Return JSON like:
{{
  "panel_summary": "one or two sentences.",
  "ordered_bubbles": [...]
}}
"""

# ---------------- Paragraph (page-level) ----------------

# Text and VLM use identical logic for paragraph mode. The payload includes:
# - page_index, page_id
# - bubbles: cleaned bubble texts (ordered)
# - allow_quotes: boolean
# - valid_quotes: list[str] (small set of verbatim quotes you may use)
PARA_SYSTEM_TEXT = """Write ONE cohesive, scene-style paragraph based ONLY on the provided lines.
Rules:
- Be concrete and grounded; no invented facts, names, or settings.
- If "allow_quotes" is true AND "valid_quotes" is non-empty, you MAY include up to TWO short verbatim quotes,
  exactly as they appear in "valid_quotes". Otherwise, DO NOT include any quotes at all.
- Keep grammar natural; remove any awkward OCR artifacts.
- Length target: 90–160 words. One paragraph only."""

PARA_USER_TEXT_TEMPLATE = """PAGE PAYLOAD (JSON):
{payload}

Return strictly JSON:
{{
  "paragraph": "one paragraph (90–160 words), following the rules."
}}
"""

PARA_SYSTEM_VLM = PARA_SYSTEM_TEXT
PARA_USER_VLM_TEMPLATE = """BUBBLES (ordered lines):
{joined}

ALSO SEE:
{{
  "allow_quotes": true_or_false,
  "valid_quotes": [...]
}}

Return strictly JSON:
{{
  "paragraph": "one paragraph (90–160 words), following the rules."
}}
"""

# ---------------- Novel mode (grounded, optional quotes) ----------------

NOVEL_SYSTEM_TEXT = """Write a short, cinematic paragraph grounded ONLY in the provided lines.
You may include brief direct quotes but only if they are present verbatim in the lines.
Keep it natural, one paragraph, 120–200 words, no inventions."""

NOVEL_USER_TEXT_TEMPLATE = """PAGE PAYLOAD (JSON):
{payload}

Return strictly JSON:
{{
  "scene_paragraph": "one paragraph",
  "cleaned_dialogue": ["Speaker 1: \\"...\\"", "Speaker 2: \\"...\\""]
}}
"""

NOVEL_SYSTEM_VLM = NOVEL_SYSTEM_TEXT
NOVEL_USER_VLM_TEMPLATE = """BUBBLES (ordered lines):
{joined}

Return strictly JSON:
{{
  "scene_paragraph": "one paragraph",
  "cleaned_dialogue": ["Speaker 1: \\"...\\"", "Speaker 2: \\"...\\""]
}}
"""

# ---------------- Repair prompt ----------------

REPAIR_SYSTEM = """You will revise a draft paragraph to be clearer and free of OCR artifacts.
Keep ONLY information grounded in the provided dialogue lines. No inventions."""

REPAIR_USER_TEMPLATE = """DIALOGUE (one per line):
{joined}

DRAFT:
{draft}

Return improved paragraph only, no extra text:
"""
