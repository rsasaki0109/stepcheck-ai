"""Parse a Markdown work procedure into a :class:`Procedure`.

Supported step syntax (mixed freely):

- Ordered lists:      ``1. Install the motherboard``
- Bulleted lists:     ``- Install the motherboard`` / ``* ...`` / ``+ ...``
- Checkbox lists:     ``- [ ] Install the motherboard``

The first ``# Heading`` becomes the procedure title. Steps keep the source order and
are re-indexed 1..N regardless of the numbers written in the file.
"""

from __future__ import annotations

import re

from stepcheck_providers import ProcedureStep

from ..domain import Procedure

_HEADING = re.compile(r"^\s*#\s+(?P<title>.+?)\s*$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(?P<text>.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(?P<text>.+?)\s*$")
_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[[ xX]?\]\s+(?P<text>.+?)\s*$")


class ProcedureParseError(ValueError):
    """Raised when a procedure contains no recognisable steps."""


def parse_procedure(markdown: str, *, default_title: str = "Procedure") -> Procedure:
    title = default_title
    texts: list[str] = []
    title_found = False

    for line in markdown.splitlines():
        if not title_found:
            heading = _HEADING.match(line)
            if heading:
                title = heading.group("title")
                title_found = True
                continue

        # Checkbox must be tried before the generic bullet rule.
        match = _CHECKBOX.match(line) or _ORDERED.match(line) or _BULLET.match(line)
        if match:
            text = match.group("text").strip()
            if text:
                texts.append(text)

    if not texts:
        raise ProcedureParseError(
            "No steps found. Use an ordered list (1., 2., ...), a bulleted list, "
            "or a checkbox list to describe each step."
        )

    steps = [ProcedureStep(index=i + 1, text=text) for i, text in enumerate(texts)]
    return Procedure(title=title, steps=steps)
