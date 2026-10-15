"""Source hashing, duplicate detection and split assignment.

Exact duplicate:      same SHA-256 of the raw bytes.
Normalized duplicate: same SHA-256 after removing comments and collapsing all whitespace runs to one
                      space. This is deliberately conservative. It does NOT catch renamed signals or
                      modules, reordered statements, different but equivalent expressions, or designs
                      that are functionally equal. It is not semantic deduplication.

Splits are assigned per design group, never per task, and before any seed variant is made, so every
variant of one design (and every task that shares its normalized source) lands in the same split.
"""
import hashlib
import re

from .verilog import strip_comments

SPLITS = (("train", 80), ("val", 90), ("test", 100))  # cumulative percent of the group hash space


def sha256(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def normalize(text):
    return re.sub(r"\s+", " ", strip_comments(text)).strip()


def split_for(group):
    """train / val / test from a fixed hash of the design group name (about 80 / 10 / 10 over many groups)."""
    bucket = int(sha256("split:" + group)[:8], 16) % 100
    return next(name for name, upper in SPLITS if bucket < upper)


class Seen:
    """Remembers raw and normalized hashes of accepted sources, in arrival order."""

    def __init__(self):
        self.raw, self.norm = {}, {}

    def check(self, text, label):
        """Return None if text is new (and remember it), else a reason naming the earlier source."""
        raw, norm = sha256(text), sha256(normalize(text))
        if raw in self.raw:
            return "exact_duplicate_of:" + self.raw[raw]
        if norm in self.norm:
            return "normalized_duplicate_of:" + self.norm[norm]
        self.raw[raw], self.norm[norm] = label, label
        return None
