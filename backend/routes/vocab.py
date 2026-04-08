from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.tokenizer import Token, tokenize
from db.models import UserVocab, Vocab, get_db

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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
