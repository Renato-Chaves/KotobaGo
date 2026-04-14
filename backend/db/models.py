import os
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/kotobago.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    native_language = Column(String, nullable=False)           # "pt", "en"
    target_language = Column(String, nullable=False)           # "ja"
    jlpt_goal = Column(Enum("N5", "N4", "N3", "N2", "N1"), nullable=False)
    target_list_id = Column(Integer, ForeignKey("lists.id"), nullable=True)
    ai_context = Column(Text, nullable=True)                   # editable AI paragraph
    model_settings = Column(JSON, nullable=True)               # per-task Ollama model overrides
    story_config = Column(JSON, nullable=True)                 # story prompt tuning: temperature, length, new_word_pct
    error_analysis_mode = Column(
        Enum("on_call", "auto"), nullable=False, default="on_call"
    )
    furigana_mode = Column(
        Enum("full", "known_only", "none"), nullable=False, default="full"
    )
    dark_mode = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    vocab = relationship("UserVocab", back_populates="user")
    target_list = relationship("List", foreign_keys=[target_list_id])


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

class Vocab(Base):
    __tablename__ = "vocab"

    id = Column(Integer, primary_key=True)
    word = Column(String, nullable=False)
    reading = Column(String, nullable=False)     # hiragana/katakana reading
    meaning = Column(Text, nullable=False)       # English meaning (seed data)
    jlpt_level = Column(Enum("N5", "N4", "N3", "N2", "N1"), nullable=True)
    list_id = Column(Integer, ForeignKey("lists.id"), nullable=True)

    user_vocab = relationship("UserVocab", back_populates="vocab")


class UserVocab(Base):
    __tablename__ = "user_vocab"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    vocab_id = Column(Integer, ForeignKey("vocab.id"), nullable=False)
    status = Column(
        Enum("unseen", "introduced", "practiced", "mastered"),
        nullable=False,
        default="unseen",
    )
    confidence = Column(
        Enum("again", "hard", "good", "easy"), nullable=True
    )
    seen_count = Column(Integer, nullable=False, default=0)
    last_seen = Column(DateTime, nullable=True)
    next_review = Column(DateTime, nullable=True)   # SM-2 calculated date
    # SM-2 internals
    interval = Column(Integer, nullable=False, default=1)       # days
    repetitions = Column(Integer, nullable=False, default=0)
    ease_factor = Column(Float, nullable=False, default=2.5)

    user = relationship("User", back_populates="vocab")
    vocab = relationship("Vocab", back_populates="user_vocab")


# ---------------------------------------------------------------------------
# Vocabulary lists (JLPT, Anki import, jpdb.io)
# ---------------------------------------------------------------------------

class List(Base):
    __tablename__ = "lists"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)      # "jlpt" | "anki" | "jpdb"
    created_at = Column(DateTime, default=datetime.utcnow)

    list_vocab = relationship("ListVocab", back_populates="list")


class ListVocab(Base):
    __tablename__ = "list_vocab"

    id = Column(Integer, primary_key=True)
    list_id = Column(Integer, ForeignKey("lists.id"), nullable=False)
    vocab_id = Column(Integer, ForeignKey("vocab.id"), nullable=False)

    list = relationship("List", back_populates="list_vocab")


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------

class Story(Base):
    __tablename__ = "stories"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=True)
    theme = Column(String, nullable=True)
    grammar_focus = Column(String, nullable=True)
    brief = Column(JSON, nullable=True)              # generated at story start, anchors the narrative
    status = Column(
        Enum("active", "completed", "abandoned"), nullable=False, default="active"
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("StorySession", back_populates="story")


class StorySession(Base):
    __tablename__ = "story_sessions"

    id = Column(Integer, primary_key=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    content_json = Column(JSON, nullable=False, default=list)       # full message history
    compressed_summary = Column(Text, nullable=True)                # auto-generated on compression
    context_tokens_used = Column(Integer, nullable=False, default=0)
    # Running stats accumulated across turns (for session summary)
    # Structure: {new_words_total, content_words_total, turn_count, errors: [{turn_index, errors: [...], overall_feedback}]}
    session_meta = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    story = relationship("Story", back_populates="sessions")
    summary = relationship("SessionSummary", back_populates="session", uselist=False)


# ---------------------------------------------------------------------------
# Session summaries
# ---------------------------------------------------------------------------

class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("story_sessions.id"), nullable=False)
    stats_json = Column(JSON, nullable=False)   # words seen, errors by type, etc.
    coach_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("StorySession", back_populates="summary")


# ---------------------------------------------------------------------------
# Grammar lessons
# ---------------------------------------------------------------------------

class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    jlpt_level = Column(Enum("N5", "N4", "N3", "N2", "N1"), nullable=False)
    content_md = Column(Text, nullable=True)    # kept for backwards compat
    stage = Column(Integer, nullable=False)     # 1, 2, 3 ...
    order = Column(Integer, nullable=False)     # position within the stage
    grammar_point = Column(String, nullable=True)  # e.g. "N1のN2"
    category = Column(String, nullable=False, default="grammar")  # grammar | vocabulary | conversation
    source_language = Column(String, nullable=True)   # language the explanation was written in
    content_json = Column(JSON, nullable=True)        # structured: {grammar_point, explanation, examples[], sentences[]}

    sessions = relationship("LessonSession", back_populates="lesson")


class LessonSession(Base):
    __tablename__ = "lesson_sessions"

    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content_json = Column(JSON, nullable=False, default=list)   # full message history
    # session_meta tracks module state — see PLAN.md for full structure
    session_meta = Column(JSON, nullable=True, default=dict)
    status = Column(
        Enum("active", "completed", "abandoned"), nullable=False, default="active"
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    lesson = relationship("Lesson", back_populates="sessions")
    summary = relationship("LessonSessionSummary", back_populates="session", uselist=False)


class LessonSessionSummary(Base):
    __tablename__ = "lesson_session_summaries"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("lesson_sessions.id"), nullable=False)
    stats_json = Column(JSON, nullable=False)
    coach_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("LessonSession", back_populates="summary")


# ---------------------------------------------------------------------------
# DB initialisation
# ---------------------------------------------------------------------------

def init_db():
    Base.metadata.create_all(bind=engine)
    # Migration: add columns that didn't exist in earlier schema versions
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE users ADD COLUMN story_config JSON",
            # Lesson table extensions (Phase 8 — Lesson Mode)
            "ALTER TABLE lessons ADD COLUMN grammar_point STRING",
            "ALTER TABLE lessons ADD COLUMN category STRING NOT NULL DEFAULT 'grammar'",
            "ALTER TABLE lessons ADD COLUMN source_language STRING",
            "ALTER TABLE lessons ADD COLUMN content_json JSON",
            "ALTER TABLE lessons ADD COLUMN content_md TEXT",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
