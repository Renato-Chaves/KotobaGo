"""
Seed JLPT vocabulary from jlpt_vocab.csv (Kaggle: robinpourtaud/jlpt-words-by-level).

Run inside the backend container for N4:
  docker compose exec backend python db/seed/seed_from_csv.py N4

Or seed multiple levels:
  docker compose exec backend python db/seed/seed_from_csv.py N4 N3 N2 N1

CSV columns: Original, Furigana, English, JLPT Level
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from db.models import List, ListVocab, SessionLocal, User, UserVocab, Vocab, init_db

CSV_PATH = os.path.join(os.path.dirname(__file__), "jlpt_vocab.csv")

VALID_LEVELS = {"N1", "N2", "N3", "N4", "N5"}


def seed_level(db, level: str, user_id: int) -> tuple[int, int]:
    """Seed one JLPT level from the CSV. Returns (inserted, skipped)."""

    # Load rows for this level from CSV
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["JLPT Level"].strip() == level:
                word = row["Original"].strip()
                reading = row["Furigana"].strip()
                meaning = row["English"].strip()
                if word and reading and meaning:
                    rows.append((word, reading, meaning))

    if not rows:
        print(f"  No rows found for {level} in CSV.")
        return 0, 0

    # Create or get the list entry
    list_name = f"JLPT {level}"
    jlpt_list = db.query(List).filter(List.name == list_name).first()
    if not jlpt_list:
        jlpt_list = List(name=list_name, source="jlpt")
        db.add(jlpt_list)
        db.flush()

    inserted = 0
    skipped = 0

    for word, reading, meaning in rows:
        existing = db.query(Vocab).filter(Vocab.word == word, Vocab.jlpt_level == level).first()
        if existing:
            skipped += 1
            continue

        vocab = Vocab(
            word=word,
            reading=reading,
            meaning=meaning,
            jlpt_level=level,
            list_id=jlpt_list.id,
        )
        db.add(vocab)
        db.flush()

        db.add(ListVocab(list_id=jlpt_list.id, vocab_id=vocab.id))

        db.add(UserVocab(
            user_id=user_id,
            vocab_id=vocab.id,
            status="unseen",
        ))

        inserted += 1

    return inserted, skipped


def main():
    levels = [a.upper() for a in sys.argv[1:]] if len(sys.argv) > 1 else ["N4"]

    for level in levels:
        if level not in VALID_LEVELS:
            print(f"Unknown level '{level}'. Valid: {', '.join(sorted(VALID_LEVELS))}")
            sys.exit(1)

    init_db()
    db = SessionLocal()

    user = db.query(User).filter(User.id == 1).first()
    if not user:
        print("User 1 not found. Run seed_user.py first.")
        db.close()
        sys.exit(1)

    for level in levels:
        print(f"Seeding {level}...")
        inserted, skipped = seed_level(db, level, user.id)
        db.commit()
        print(f"  {level} done: {inserted} inserted, {skipped} skipped.")

    db.close()


if __name__ == "__main__":
    main()
