from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.llm import router as llm_router
from core.srs import Rating, SRSState, confidence_to_status, next_state
from core.tokenizer import Token, tokenize
from db.models import User, UserVocab, Vocab, get_db

router = APIRouter(prefix="/vocab", tags=["vocab"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TokenizeRequest(BaseModel):
    text: str
    user_id: int = 1   # single-user app for now


class TokenOut(BaseModel):
    surface: str
    reading: str
    pos: str
    is_content: bool
    status: str
    vocab_id: int | None


class TokenizeResponse(BaseModel):
    tokens: list[TokenOut]


class LookupResponse(BaseModel):
    vocab_id: int
    word: str
    reading: str
    meaning: str
    jlpt_level: str | None
    explanation: str          # LLM explanation in user's native language
    jisho_url: str
    user_status: str
    next_review: datetime | None


class RateRequest(BaseModel):
    vocab_id: int
    user_id: int = 1
    rating: Rating            # "again" | "hard" | "good" | "easy"


class RateResponse(BaseModel):
    vocab_id: int
    new_status: str
    next_review: datetime
    interval_days: int


class VocabGridItem(BaseModel):
    vocab_id: int
    word: str
    reading: str
    meaning: str
    jlpt_level: str | None
    status: str                   # "unseen" | "introduced" | "practiced" | "mastered"
    next_review: datetime | None
    interval_days: int
    is_due: bool                  # True when next_review <= now and status != unseen


class VocabGridResponse(BaseModel):
    items: list[VocabGridItem]
    total: int
    stats: dict                   # {unseen, introduced, practiced, mastered, due}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/lookup/{vocab_id}", response_model=LookupResponse)
async def lookup_word(vocab_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    """
    Return full dictionary info for a word plus an LLM-generated
    explanation in the user's native language.
    """
    vocab = db.query(Vocab).filter(Vocab.id == vocab_id).first()
    if not vocab:
        raise HTTPException(status_code=404, detail="Word not found")

    user = db.query(User).filter(User.id == user_id).first()
    native = user.native_language if user else "en"

    user_vocab = (
        db.query(UserVocab)
        .filter(UserVocab.user_id == user_id, UserVocab.vocab_id == vocab_id)
        .first()
    )

    explanation = await _generate_explanation(vocab, native)

    return LookupResponse(
        vocab_id=vocab.id,
        word=vocab.word,
        reading=vocab.reading,
        meaning=vocab.meaning,
        jlpt_level=vocab.jlpt_level,
        explanation=explanation,
        jisho_url=f"https://jisho.org/search/{vocab.word}",
        user_status=user_vocab.status if user_vocab else "unseen",
        next_review=user_vocab.next_review if user_vocab else None,
    )


@router.post("/rate", response_model=RateResponse)
async def rate_word(req: RateRequest, db: Session = Depends(get_db)):
    """
    Record a confidence rating for a word and update its SM-2 schedule.
    """
    user_vocab = (
        db.query(UserVocab)
        .filter(UserVocab.user_id == req.user_id, UserVocab.vocab_id == req.vocab_id)
        .first()
    )
    if not user_vocab:
        raise HTTPException(status_code=404, detail="UserVocab record not found")

    current = SRSState(
        interval=user_vocab.interval,
        repetitions=user_vocab.repetitions,
        ease_factor=user_vocab.ease_factor,
    )
    new_srs, next_review = next_state(current, req.rating)

    user_vocab.interval = new_srs.interval
    user_vocab.repetitions = new_srs.repetitions
    user_vocab.ease_factor = new_srs.ease_factor
    user_vocab.confidence = req.rating
    user_vocab.status = confidence_to_status(req.rating)
    user_vocab.next_review = next_review
    user_vocab.last_seen = datetime.utcnow()
    user_vocab.seen_count = (user_vocab.seen_count or 0) + 1

    db.commit()

    return RateResponse(
        vocab_id=req.vocab_id,
        new_status=user_vocab.status,
        next_review=next_review,
        interval_days=new_srs.interval,
    )


@router.get("/grid", response_model=VocabGridResponse)
async def get_vocab_grid(
    user_id: int = 1,
    status: str = "all",   # "all" | "unseen" | "introduced" | "practiced" | "mastered" | "due"
    jlpt: str = "all",     # "all" | "N5" | "N4" | "N3" | "N2" | "N1"
    db: Session = Depends(get_db),
):
    """
    Return the user's full vocabulary grid with optional filters.
    Words are sorted: due first, then by status progression, then alphabetically.
    """
    now = datetime.utcnow()

    query = (
        db.query(UserVocab, Vocab)
        .join(Vocab, UserVocab.vocab_id == Vocab.id)
        .filter(UserVocab.user_id == user_id)
    )

    if jlpt != "all":
        query = query.filter(Vocab.jlpt_level == jlpt)

    rows = query.all()

    # Build stats over the full (unfiltered-by-status) result set
    status_counts = {"unseen": 0, "introduced": 0, "practiced": 0, "mastered": 0, "due": 0}
    for uv, _ in rows:
        if uv.status in status_counts:
            status_counts[uv.status] += 1
        if uv.next_review and uv.next_review <= now and uv.status != "unseen":
            status_counts["due"] += 1

    # Apply status filter AFTER computing stats
    def _matches_filter(uv: UserVocab) -> bool:
        if status == "all":
            return True
        if status == "due":
            return bool(uv.next_review and uv.next_review <= now and uv.status != "unseen")
        return uv.status == status

    items: list[VocabGridItem] = []
    for uv, vocab in rows:
        if not _matches_filter(uv):
            continue
        is_due = bool(uv.next_review and uv.next_review <= now and uv.status != "unseen")
        items.append(VocabGridItem(
            vocab_id=vocab.id,
            word=vocab.word,
            reading=vocab.reading,
            meaning=vocab.meaning,
            jlpt_level=vocab.jlpt_level,
            status=uv.status,
            next_review=uv.next_review,
            interval_days=uv.interval,
            is_due=is_due,
        ))

    # Sort: due first, then introduced > practiced > mastered > unseen, then word
    _status_order = {"introduced": 0, "practiced": 1, "mastered": 2, "unseen": 3}
    items.sort(key=lambda x: (not x.is_due, _status_order.get(x.status, 9), x.word))

    return VocabGridResponse(
        items=items,
        total=len(items),
        stats=status_counts,
    )


@router.post("/tokenize", response_model=TokenizeResponse)
async def tokenize_text(req: TokenizeRequest, db: Session = Depends(get_db)):
    """
    Tokenize Japanese text and annotate each token with the user's
    vocab status (known / new / unseen).
    """
    tokens = tokenize(req.text)
    annotated = _annotate_with_vocab_status(tokens, req.user_id, db)
    return TokenizeResponse(tokens=[
        TokenOut(
            surface=t.surface,
            reading=t.reading,
            pos=t.pos,
            is_content=t.is_content,
            status=t.status,
            vocab_id=t.vocab_id,
        )
        for t in annotated
    ])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _annotate_with_vocab_status(
    tokens: list[Token], user_id: int, db: Session
) -> list[Token]:
    """
    Look up each content token against user_vocab and set its status.

    Non-content tokens (particles, punctuation) stay 'unseen' — they're
    not tracked in SRS and don't need a status for display purposes.
    """
    surfaces = {t.surface for t in tokens if t.is_content}
    if not surfaces:
        return tokens

    # Single query: join UserVocab → Vocab for all surfaces at once
    rows = (
        db.query(UserVocab, Vocab)
        .join(Vocab, UserVocab.vocab_id == Vocab.id)
        .filter(UserVocab.user_id == user_id, Vocab.word.in_(surfaces))
        .all()
    )

    # Build a lookup map: surface → (status, vocab_id)
    status_map: dict[str, tuple[str, int]] = {
        vocab.word: (uv.status, vocab.id) for uv, vocab in rows
    }

    for token in tokens:
        if not token.is_content:
            continue
        if token.surface in status_map:
            status, vocab_id = status_map[token.surface]
            token.status = "known" if status in ("practiced", "mastered") else "new"
            token.vocab_id = vocab_id
        # else: stays "unseen" — word not in user's vocab list at all

    return tokens


async def _generate_explanation(vocab: Vocab, native_language: str) -> str:
    """Generate a short explanation of the word in the user's native language."""
    lang_name = {"pt": "Portuguese", "en": "English", "ja": "Japanese"}.get(
        native_language, native_language
    )
    system = (
        f"You are a Japanese language tutor. Explain Japanese words clearly and concisely in {lang_name}. "
        "Include: meaning, typical usage context, and one natural example sentence with translation. "
        "Keep the response under 80 words."
    )
    messages = [{"role": "user", "content": f"Explain the Japanese word: {vocab.word} ({vocab.reading}) — {vocab.meaning}"}]
    try:
        return await llm_router.route("story", system, messages)
    except Exception:
        # Fall back to the seed meaning if LLM is unavailable
        return vocab.meaning
