"""
Seed the default user (id=1) for local development.
Run inside the backend container:
  docker compose exec backend python db/seed/seed_user.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from db.models import SessionLocal, User, init_db

init_db()

db = SessionLocal()

existing = db.query(User).filter(User.id == 1).first()
if existing:
    print("User 1 already exists — skipping.")
else:
    user = User(
        native_language="pt",
        target_language="ja",
        jlpt_goal="N5",
        ai_context=(
            "Portuguese-speaking Japanese learner at N5 level. "
            "Interested in anime, gaming, and everyday life topics. "
            "Prefers short sentences and familiar vocabulary."
        ),
        error_analysis_mode="on_call",
        furigana_mode="full",
        dark_mode=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"Created user id={user.id}: {user.native_language} → {user.target_language} ({user.jlpt_goal})")

db.close()
