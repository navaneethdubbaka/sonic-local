from __future__ import annotations

import re

_REFUSE_PATTERNS = [
    r"\bdelete all\b",
    r"\bwipe\b.*(drive|disk|files)\b",
    r"\bbuy\b.*(card|product|ticket)\b",
    r"\bpurchase\b",
    r"\btransfer money\b",
    r"\bsend (an )?email\b",
    r"\bchange (my )?(google )?password\b",
    r"\bdisable (windows )?defender\b",
    r"\bdisable security\b",
]


def is_hard_refuse(utterance: str) -> bool:
    text = utterance.lower()
    return any(re.search(p, text) for p in _REFUSE_PATTERNS)
