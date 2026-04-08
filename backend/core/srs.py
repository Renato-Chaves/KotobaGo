"""
SM-2 spaced repetition algorithm — same as Anki.

The algorithm takes the current SRS state of a word and a quality rating
(0–5), and returns the updated state with the next review date.

Rating mapping from our 4-button UI:
  Again → 0  (complete blackout, reset)
  Hard  → 3  (correct but difficult)
  Good  → 4  (correct with some hesitation)
  Easy  → 5  (perfect recall)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

Rating = Literal["again", "hard", "good", "easy"]

# Numeric quality score per button
_QUALITY: dict[Rating, int] = {
    "again": 0,
    "hard":  3,
    "good":  4,
    "easy":  5,
}


@dataclass
class SRSState:
    interval: int       # days until next review
    repetitions: int    # number of successful reviews in a row
    ease_factor: float  # multiplier for interval growth (min 1.3)


def next_state(current: SRSState, rating: Rating) -> tuple[SRSState, datetime]:
    """
    Compute the next SRS state and review date from a rating.

    Returns (new_state, next_review_datetime).
    """
    q = _QUALITY[rating]
    reps = current.repetitions
    ef = current.ease_factor
    interval = current.interval

    if q < 3:
        # Failed — reset repetitions, short review interval
        reps = 0
        interval = 1
    else:
        # Passed — advance
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = round(interval * ef)
        reps += 1

    # Update ease factor (SM-2 formula)
    ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    ef = max(1.3, ef)  # floor at 1.3

    new_state = SRSState(interval=interval, repetitions=reps, ease_factor=ef)
    next_review = datetime.utcnow() + timedelta(days=interval)
    return new_state, next_review


def confidence_to_status(rating: Rating) -> str:
    """Map a confidence rating to a UserVocab status string."""
    if rating == "again":
        return "introduced"
    if rating == "hard":
        return "practiced"
    return "mastered"  # good or easy
