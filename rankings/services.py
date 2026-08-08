import hashlib
import math
import random
from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q

from universities.models import University

from .baseline import (
    DEFAULT_BASE_RATING,
    baseline_defaults,
    baseline_rating_for_name,
    ranking_university_queryset,
)
from .models import ComparisonVote, PersonalResult, RankingBoard, UniversityRating, VoteSession


DEFAULT_BOARDS = [
    ("overall", "종합", "전체적인 대학 선호도", 10),
]

LEGACY_BOARD_SLUGS = ("employment", "campus", "recognition")


def ensure_default_boards():
    """Expose a single overall board and retire the old split boards.

    Historical votes/ratings are not deleted; the old boards are simply marked inactive.
    """
    board, _ = RankingBoard.objects.get_or_create(
        slug="overall",
        defaults={
            "name": "종합",
            "description": "전체적인 대학 선호도",
            "display_order": 10,
            "is_active": True,
        },
    )
    changed = []
    if board.name != "종합":
        board.name = "종합"
        changed.append("name")
    if board.description != "전체적인 대학 선호도":
        board.description = "전체적인 대학 선호도"
        changed.append("description")
    if not board.is_active:
        board.is_active = True
        changed.append("is_active")
    if changed:
        changed.append("updated_at")
        board.save(update_fields=changed)

    RankingBoard.objects.filter(slug__in=LEGACY_BOARD_SLUGS).update(is_active=False)
    return [board]


def _hash_ip(ip):
    if not ip:
        return ""
    payload = f"{settings.SECRET_KEY}:{ip}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_vote_session(request):
    if not request.session.session_key:
        request.session.create()

    session_key = request.session.session_key
    user = request.user if request.user.is_authenticated else None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")

    vote_session = (
        VoteSession.objects.filter(session_key=session_key)
        .order_by("-last_seen_at")
        .first()
    )

    if vote_session is None:
        vote_session = VoteSession.objects.create(
            session_key=session_key,
            user=user,
            ip_hash=_hash_ip(ip),
        )
    elif user and vote_session.user_id != user.id:
        vote_session.user = user
        vote_session.save(update_fields=["user", "last_seen_at"])

    return vote_session


def get_or_create_rating(board, university):
    return UniversityRating.objects.get_or_create(
        board=board,
        university=university,
        defaults=baseline_defaults(board, university),
    )[0]


def select_pair(board, vote_session):
    """Pick an informative matchup instead of a fully random pair.

    The default mix is intentionally conservative:
    - ~80% close/neighbor matchups
    - ~15% one-tier challenge matchups
    - ~5% exploration matchups for under-tested universities

    Recent universities and recent pairs in the same browser session receive a
    large cooldown penalty so the screen does not feel repetitive.
    """
    universities = list(
        ranking_university_queryset().only(
            "university_id",
            "name",
            "logo_path",
            "region",
            "address",
        )
    )
    if len(universities) < 2:
        return None

    university_by_id = {u.pk: u for u in universities}
    university_ids = list(university_by_id)

    rating_map = {
        rating.university_id: rating
        for rating in UniversityRating.objects.filter(
            board=board,
            university_id__in=university_ids,
        )
    }

    def state(university_id):
        rating = rating_map.get(university_id)
        university = university_by_id[university_id]
        if rating is not None:
            return rating.rating, rating.rating_deviation, rating.match_count
        return (
            baseline_rating_for_name(university.name, board.slug),
            350.0,
            0,
        )

    # Session-local history is enough to keep the UI varied without needing
    # another table or cache. Age 0 means the immediately previous matchup.
    recent_votes = list(
        ComparisonVote.objects.filter(session=vote_session, board=board)
        .order_by("-created_at", "-vote_id")
        .values_list("university_a_id", "university_b_id")[:80]
    )
    recent_pairs = {frozenset(pair) for pair in recent_votes[:60]}
    recent_age = {}
    for age, pair in enumerate(recent_votes):
        for university_id in pair:
            recent_age.setdefault(university_id, age)

    # Current ladder position is another useful distance signal when many
    # universities have similar ratings.
    ordered_ids = sorted(
        university_ids,
        key=lambda uid: (-state(uid)[0], university_by_id[uid].name),
    )
    rank_index = {uid: index for index, uid in enumerate(ordered_ids)}

    # Anchor selection prioritizes under-exposed / uncertain universities, but
    # strongly avoids schools shown in the last few comparisons.
    anchor_scores = []
    for uid in university_ids:
        _rating, rd, matches = state(uid)
        age = recent_age.get(uid)
        cooldown_penalty = 0.0
        if age is not None and age < 4:
            cooldown_penalty = 10000.0
        elif age is not None and age < 10:
            cooldown_penalty = 900.0

        exposure_penalty = min(matches, 60) * 7.0
        uncertainty_bonus = min(rd, 350.0) * 0.28
        new_school_bonus = 180.0 if matches == 0 else max(0, 8 - matches) * 12.0
        score = (
            cooldown_penalty
            + exposure_penalty
            - uncertainty_bonus
            - new_school_bonus
            + random.random() * 28.0
        )
        anchor_scores.append((score, uid))

    anchor_scores.sort(key=lambda item: item[0])
    anchor_pool = anchor_scores[: min(14, len(anchor_scores))]
    first_id = random.choice(anchor_pool)[1]
    first_rating, _first_rd, _first_matches = state(first_id)
    first_rank = rank_index[first_id]

    # Most matchups are close enough to be informative. Challenge matches
    # occasionally test a school against the next tier, while exploration
    # keeps new/uncertain schools from becoming stranded at their seed.
    roll = random.random()
    if roll < 0.80:
        mode = "close"
    elif roll < 0.95:
        mode = "challenge"
    else:
        mode = "explore"

    opponent_scores = []
    for uid in university_ids:
        if uid == first_id:
            continue

        rating, rd, matches = state(uid)
        pair = frozenset((first_id, uid))
        rating_gap = abs(first_rating - rating)
        rank_gap = abs(first_rank - rank_index[uid])
        age = recent_age.get(uid)

        repeat_penalty = 50000.0 if pair in recent_pairs else 0.0
        recent_school_penalty = 0.0
        if age is not None and age < 3:
            recent_school_penalty = 5000.0
        elif age is not None and age < 7:
            recent_school_penalty = 500.0

        if mode == "close":
            # Neighboring ladder positions and roughly <=100 rating gap are
            # overwhelmingly preferred.
            mode_score = (
                rating_gap * 0.45
                + rank_gap * 8.0
                + max(0.0, rating_gap - 110.0) * 4.0
                + max(0, rank_gap - 7) * 90.0
            )
        elif mode == "challenge":
            # Aim around a 70~150 point gap: enough for an upset test without
            # wasting votes on top-vs-bottom mismatches.
            mode_score = (
                abs(rating_gap - 110.0) * 0.55
                + rank_gap * 3.0
                + max(0, rank_gap - 15) * 65.0
            )
        else:
            # A small amount of exploration favors uncertain and under-played
            # schools, while still mildly preferring reasonable distance.
            uncertainty_bonus = min(rd, 350.0) * 0.35
            underplayed_bonus = max(0, 12 - matches) * 10.0
            mode_score = rating_gap * 0.18 + rank_gap * 1.5 - uncertainty_bonus - underplayed_bonus

        score = (
            repeat_penalty
            + recent_school_penalty
            + mode_score
            + random.random() * 20.0
        )
        opponent_scores.append((score, uid))

    opponent_scores.sort(key=lambda item: item[0])
    opponent_pool = opponent_scores[: min(5, len(opponent_scores))]
    second_id = random.choice(opponent_pool)[1]

    pair = [university_by_id[first_id], university_by_id[second_id]]
    random.shuffle(pair)
    return pair


_GLICKO_SCALE = 173.7178
_GLICKO_TAU = 0.5
_GLICKO_EPSILON = 0.000001


def _g(phi):
    return 1 / math.sqrt(1 + 3 * phi * phi / (math.pi * math.pi))


def _e(mu, opponent_mu, opponent_phi):
    return 1 / (1 + math.exp(-_g(opponent_phi) * (mu - opponent_mu)))


def _new_volatility(phi, sigma, delta, variance):
    a = math.log(sigma * sigma)

    def f(x):
        ex = math.exp(x)
        numerator = ex * (delta * delta - phi * phi - variance - ex)
        denominator = 2 * ((phi * phi + variance + ex) ** 2)
        return numerator / denominator - (x - a) / (_GLICKO_TAU * _GLICKO_TAU)

    A = a
    if delta * delta > phi * phi + variance:
        B = math.log(delta * delta - phi * phi - variance)
    else:
        k = 1
        while f(a - k * _GLICKO_TAU) < 0:
            k += 1
        B = a - k * _GLICKO_TAU

    fA = f(A)
    fB = f(B)

    while abs(B - A) > _GLICKO_EPSILON:
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)
        if fC * fB < 0:
            A, fA = B, fB
        else:
            fA /= 2
        B, fB = C, fC

    return math.exp(A / 2)


def glicko2_update(rating, rd, volatility, opponent_rating, opponent_rd, score):
    mu = (rating - 1500) / _GLICKO_SCALE
    phi = rd / _GLICKO_SCALE
    opponent_mu = (opponent_rating - 1500) / _GLICKO_SCALE
    opponent_phi = opponent_rd / _GLICKO_SCALE

    g = _g(opponent_phi)
    expected = _e(mu, opponent_mu, opponent_phi)
    variance = 1 / (g * g * expected * (1 - expected))
    delta = variance * g * (score - expected)

    new_sigma = _new_volatility(phi, volatility, delta, variance)
    phi_star = math.sqrt(phi * phi + new_sigma * new_sigma)
    new_phi = 1 / math.sqrt(1 / (phi_star * phi_star) + 1 / variance)
    new_mu = mu + new_phi * new_phi * g * (score - expected)

    new_rating = 1500 + _GLICKO_SCALE * new_mu
    new_rd = _GLICKO_SCALE * new_phi

    return new_rating, max(30.0, min(350.0, new_rd)), new_sigma


def _is_seeded_rating(rating_obj):
    board_slug = getattr(getattr(rating_obj, "board", None), "slug", "overall")
    baseline = baseline_rating_for_name(rating_obj.university.name, board_slug)
    return abs(baseline - DEFAULT_BASE_RATING) > 0.001


def _effective_rd(rating_obj):
    """Limit first-vote volatility while keeping unseeded schools calibratable."""
    stored = max(30.0, min(350.0, float(rating_obj.rating_deviation)))
    cap = 95.0 if _is_seeded_rating(rating_obj) else 150.0
    return min(stored, cap)


def _rating_step_cap(rating_obj):
    # Seeded schools represent an explicit prior and should move gradually.
    # Unseeded schools are allowed to find their level somewhat faster.
    if _is_seeded_rating(rating_obj):
        return 14.0 if rating_obj.match_count < 25 else 11.0
    return 22.0 if rating_obj.match_count < 20 else 16.0


def _bounded_rating(before, proposed, cap, impact_weight):
    if impact_weight <= 0:
        return before
    blended = before + (proposed - before) * impact_weight
    weighted_cap = cap * impact_weight
    delta = max(-weighted_cap, min(weighted_cap, blended - before))
    return before + delta


def _apply_result(
    rating_a,
    rating_b,
    selected_university_id,
    impact_weight=1.0,
):
    a_before = (rating_a.rating, _effective_rd(rating_a), rating_a.volatility)
    b_before = (rating_b.rating, _effective_rd(rating_b), rating_b.volatility)

    score_a = 1.0 if selected_university_id == rating_a.university_id else 0.0
    score_b = 1.0 - score_a

    a_after = glicko2_update(
        *a_before,
        b_before[0],
        b_before[1],
        score_a,
    )
    b_after = glicko2_update(
        *b_before,
        a_before[0],
        a_before[1],
        score_b,
    )

    if impact_weight > 0:
        rating_a.rating = _bounded_rating(
            a_before[0],
            a_after[0],
            _rating_step_cap(rating_a),
            impact_weight,
        )
        rating_b.rating = _bounded_rating(
            b_before[0],
            b_after[0],
            _rating_step_cap(rating_b),
            impact_weight,
        )
        rating_a.rating_deviation = a_after[1]
        rating_b.rating_deviation = b_after[1]
        rating_a.volatility = a_after[2]
        rating_b.volatility = b_after[2]

    rating_a.match_count += 1
    rating_b.match_count += 1

    if score_a == 1.0:
        rating_a.win_count += 1
        rating_b.loss_count += 1
    else:
        rating_b.win_count += 1
        rating_a.loss_count += 1

    rating_a.save()
    rating_b.save()


def record_vote(board, vote_session, university_a, university_b, selected_university=None, skipped=False):
    if university_a.pk == university_b.pk:
        raise ValueError("같은 대학끼리는 투표할 수 없습니다.")

    if skipped:
        selected_university = None
    elif selected_university is None or selected_university.pk not in {university_a.pk, university_b.pk}:
        raise ValueError("올바른 대학을 선택해주세요.")

    with transaction.atomic():
        # Repeated votes for the exact same pair from one browser/session are
        # still recorded as real participation, but their rating influence is
        # damped to make simple refresh/spam much less effective.
        previous_pair_votes = ComparisonVote.objects.filter(
            session=vote_session,
            board=board,
            skipped=False,
        ).filter(
            Q(university_a=university_a, university_b=university_b)
            | Q(university_a=university_b, university_b=university_a)
        ).count()
        if previous_pair_votes == 0:
            impact_weight = 1.0
        elif previous_pair_votes == 1:
            impact_weight = 0.35
        else:
            impact_weight = 0.0

        vote = ComparisonVote(
            board=board,
            session=vote_session,
            university_a=university_a,
            university_b=university_b,
            selected_university=selected_university,
            skipped=skipped,
        )
        vote.full_clean()
        vote.save()

        VoteSession.objects.filter(pk=vote_session.pk).update(vote_count=F("vote_count") + 1)

        if not skipped:
            rating_a, _ = UniversityRating.objects.select_for_update().get_or_create(
                board=board,
                university=university_a,
                defaults=baseline_defaults(board, university_a),
            )
            rating_b, _ = UniversityRating.objects.select_for_update().get_or_create(
                board=board,
                university=university_b,
                defaults=baseline_defaults(board, university_b),
            )
            _apply_result(
                rating_a,
                rating_b,
                selected_university.pk,
                impact_weight=impact_weight,
            )

    vote_session.refresh_from_db(fields=["vote_count"])
    return vote


def build_personal_result(vote_session, board):
    votes = list(
        ComparisonVote.objects.filter(
            session=vote_session,
            board=board,
            skipped=False,
        )
        .select_related("university_a", "university_b", "selected_university")
        .order_by("created_at", "vote_id")
    )

    scores = defaultdict(lambda: 1500.0)
    wins = defaultdict(int)
    losses = defaultdict(int)
    universities = {}
    k = 32.0

    for vote in votes:
        a = vote.university_a
        b = vote.university_b
        universities[a.pk] = a
        universities[b.pk] = b

        ra = scores[a.pk]
        rb = scores[b.pk]
        expected_a = 1 / (1 + 10 ** ((rb - ra) / 400))
        result_a = 1.0 if vote.selected_university_id == a.pk else 0.0

        scores[a.pk] = ra + k * (result_a - expected_a)
        scores[b.pk] = rb + k * ((1 - result_a) - (1 - expected_a))

        if result_a == 1.0:
            wins[a.pk] += 1
            losses[b.pk] += 1
        else:
            wins[b.pk] += 1
            losses[a.pk] += 1

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:10]
    top10 = []

    for rank, (university_id, score) in enumerate(ranked, start=1):
        university = universities[university_id]
        top10.append(
            {
                "rank": rank,
                "university_id": university_id,
                "name": university.name,
                "logo_path": university.logo_path,
                "score": round(score, 1),
                "wins": wins[university_id],
                "losses": losses[university_id],
            }
        )

    payload = {
        "board": {"slug": board.slug, "name": board.name},
        "total_votes": len(votes),
        "top10": top10,
    }

    return PersonalResult.objects.create(
        session=vote_session,
        board=board,
        vote_count=len(votes),
        result_json=payload,
    )
