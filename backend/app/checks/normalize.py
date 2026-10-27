"""Text normalisation shared by quote verification.

Both the source text and each quote go through the same function, so a quote
matches when it differs only in whitespace, quote style, dash style, bullets,
PDF ligatures or case.
"""

import re
import unicodedata

_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "´": "'", "`": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"', "»": '"',
})
_DASHES = re.compile(r"[‐‑‒–—―−­]")
_BULLETS = re.compile(r"[•‣▪●◦⁃∙·]")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # ﬁ → fi, non-breaking spaces → spaces
    text = text.translate(_QUOTES)
    text = _DASHES.sub("-", text)
    text = _BULLETS.sub(" ", text)
    text = _WS.sub(" ", text)
    return text.strip().casefold()


def contains(source_normalized: str, quote: str) -> bool:
    q = normalize(quote).strip(" .;,")
    return bool(q) and q in source_normalized
