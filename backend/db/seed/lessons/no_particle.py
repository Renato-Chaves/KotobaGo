"""
Seed: の particle lesson (N5)

Grammar point: N1のN2 — の connects two nouns, where N1 modifies N2.
Equivalent to "de" / "do" / "da" in Portuguese, or "'s" / "of" in English.
"""

from db.models import Lesson, SessionLocal

LESSON_DATA = {
    "grammar_point": "N1のN2",
    "source_language": "en",
    "explanation": (
        "The particle の connects two nouns. N1 describes or owns N2. "
        "Think of it as 's in English or 'de/do/da' in Portuguese. "
        "Examples: 日本の食べ物 = Japanese food (food OF Japan), "
        "わたしの本 = my book (book OF me / my book)."
    ),
    "examples": [
        {"id": "ex_1", "japanese": "もりのくま",     "reading": "もりのくま",     "translation": "bear of the forest"},
        {"id": "ex_2", "japanese": "にほんのたべもの", "reading": "にほんのたべもの", "translation": "Japanese food"},
        {"id": "ex_3", "japanese": "わたしのほん",    "reading": "わたしのほん",    "translation": "my book"},
        {"id": "ex_4", "japanese": "がっこうのせんせい","reading": "がっこうのせんせい","translation": "school teacher"},
        {"id": "ex_5", "japanese": "ともだちのなまえ", "reading": "ともだちのなまえ", "translation": "friend's name"},
    ],
    "sentences": [
        {
            "id": "s_1",
            "japanese": "ブラジルのたべものはおいしい！",
            "reading":  "ブラジルのたべものはおいしい！",
            "translation": "Brazilian food is delicious!",
        },
        {
            "id": "s_2",
            "japanese": "これはわたしのかばんです。",
            "reading":  "これはわたしのかばんです。",
            "translation": "This is my bag.",
        },
        {
            "id": "s_3",
            "japanese": "あのひとはにほんのがくせいですか？",
            "reading":  "あのひとはにほんのがくせいですか？",
            "translation": "Is that person a Japanese student?",
        },
        {
            "id": "s_4",
            "japanese": "わたしのともだちのなまえはサクラです。",
            "reading":  "わたしのともだちのなまえはサクラです。",
            "translation": "My friend's name is Sakura.",
        },
    ],
}


def seed(db=None):
    """Insert the の particle lesson if it doesn't already exist."""
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        existing = db.query(Lesson).filter_by(grammar_point="N1のN2").first()
        if existing:
            return  # already seeded

        lesson = Lesson(
            title="The の Particle — Connecting Nouns",
            jlpt_level="N5",
            grammar_point="N1のN2",
            category="grammar",
            source_language="en",
            stage=1,
            order=1,
            content_md="",          # legacy column, kept non-null for existing schema compat
            content_json=LESSON_DATA,
        )
        db.add(lesson)
        db.commit()
        print("[seed] の particle lesson inserted.")
    finally:
        if close:
            db.close()


if __name__ == "__main__":
    seed()
