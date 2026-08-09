"""Clean-start rating defaults.

K-unirank no longer uses operator-defined university ranking seeds.
Every university begins from the same neutral Glicko-2 state and only
real ComparisonVote records affect ratings and match/win/loss counts.
"""

DEFAULT_BASE_RATING = 1500.0
DEFAULT_BASE_RD = 350.0

# Kept for compatibility with older imports/commands.
OVERALL_BASELINE = []


def normalize_name(value: str) -> str:
    return (value or "").strip().lower()


def baseline_rating_for_name(name: str, board_slug: str = "overall") -> float:
    """All universities start from the same neutral rating."""
    return DEFAULT_BASE_RATING


def baseline_defaults(board, university) -> dict:
    return {
        "rating": DEFAULT_BASE_RATING,
        "rating_deviation": DEFAULT_BASE_RD,
        "volatility": 0.06,
        "match_count": 0,
        "win_count": 0,
        "loss_count": 0,
    }


def is_ranking_eligible_name(name: str) -> bool:
    return bool((name or "").strip())


def ranking_university_queryset():
    from universities.models import University
    return University.objects.filter(is_active=True)


def seed_sample_count_for_name(name: str, board_slug: str = "overall") -> int:
    """Legacy compatibility: synthetic samples are no longer used."""
    return 0


def display_match_count_for_rating(rating_obj) -> int:
    """Display only real user comparisons."""
    return int(getattr(rating_obj, "match_count", 0) or 0)
