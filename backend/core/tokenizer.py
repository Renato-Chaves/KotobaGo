from dataclasses import dataclass
from typing import Literal

import fugashi

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

VocabStatus = Literal["known", "new", "unseen"]


@dataclass
class Token:
    surface: str        # the actual text as it appears ("学生")
    reading: str        # hiragana reading ("がくせい")
    pos: str            # part of speech ("名詞", "助詞", etc.)
    is_content: bool    # False for particles, punctuation, spaces — skip SRS
    status: VocabStatus = "unseen"
    vocab_id: int | None = None


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# fugashi.Tagger() uses the bundled unidic-lite dictionary automatically —
# no system MeCab config path needed. Unidic gives us named feature fields
# (word.feature.pos1, word.feature.pron) instead of positional CSV parsing.
_tagger = fugashi.Tagger()

# UniDic part-of-speech tags worth tracking for SRS.
# Particles (助詞), auxiliary verbs (助動詞), punctuation, and symbols are
# excluded — they're covered by grammar lessons, not vocab SRS.
_CONTENT_POS = {"名詞", "代名詞", "動詞", "形容詞", "形容動詞", "副詞", "接続詞", "感動詞"}


def tokenize(text: str) -> list[Token]:
    """
    Tokenize Japanese text into a list of Token objects.

    Each token carries its surface form, reading, part of speech, and
    whether it's a content word worth tracking in SRS. Vocab status
    defaults to 'unseen' — callers annotate with actual status from DB.
    """
    tokens: list[Token] = []

    for word in _tagger(text):
        surface = word.surface
        feature = word.feature

        pos = feature.pos1 if feature.pos1 else "UNK"

        # lForm (lemma reading form) gives the canonical katakana reading —
        # e.g. ガクセイ, ベンキョウ. Prefer it over pron, which uses ー for
        # long vowels (spoken form) and would give ガクセー, ベンキョー.
        raw_reading = (
            feature.lForm
            if feature.lForm and feature.lForm != "*"
            else feature.pron
            if feature.pron and feature.pron != "*"
            else surface
        )
        reading = _to_hiragana(raw_reading)

        tokens.append(Token(
            surface=surface,
            reading=reading,
            pos=pos,
            is_content=pos in _CONTENT_POS,
        ))

    return tokens


def _to_hiragana(text: str) -> str:
    """Convert katakana characters to hiragana. Leaves other characters unchanged."""
    return "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ン" else c
        for c in text
    )
