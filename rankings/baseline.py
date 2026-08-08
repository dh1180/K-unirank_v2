"""Transparent initial priors for the overall university preference board.

These are NOT user votes. They are operator-defined starting ratings so that a
new/empty board does not begin with every university tied at 1500.

Live VS votes update UniversityRating from these starting values using the
existing Glicko-2 implementation.
"""

from __future__ import annotations

import re


DEFAULT_BASE_RATING = 1200.0
DEFAULT_BASE_RD = 350.0
SEEDED_RD = 220.0

# Ordered seed requested for the overall preference board.
# Larger rating = higher initial position. Values deliberately leave room for
# live votes to move schools over time.
#
# name, initial_rating
OVERALL_BASELINE = [
    ("서울대학교", 1960.0),
    ("한국과학기술원", 1945.0),
    ("포항공과대학교", 1930.0),
    ("연세대학교", 1915.0),
    ("고려대학교", 1900.0),

    # 서성한 + 과기원 그룹
    ("서강대학교", 1840.0),
    ("성균관대학교", 1828.0),
    ("한양대학교", 1816.0),
    ("울산과학기술원", 1804.0),
    ("광주과학기술원", 1792.0),
    ("대구경북과학기술원", 1780.0),

    # 중경외시 + 이화 + 사관학교
    ("중앙대학교", 1725.0),
    ("경희대학교", 1713.0),
    ("한국외국어대학교", 1701.0),
    ("서울시립대학교", 1689.0),
    ("이화여자대학교", 1677.0),
    ("육군사관학교", 1665.0),
    ("공군사관학교", 1653.0),
    ("해군사관학교", 1641.0),

    # 건동홍 및 수도권/거점 상위권
    ("건국대학교", 1590.0),
    ("동국대학교", 1578.0),
    ("홍익대학교", 1566.0),
    ("아주대학교", 1554.0),
    ("인하대학교", 1542.0),
    ("부산대학교", 1530.0),
    ("경북대학교", 1518.0),
    ("한양대학교 ERICA캠퍼스", 1490.0),

    # 국숭세단 + 항공/과기/숙명
    ("국민대학교", 1470.0),
    ("숭실대학교", 1458.0),
    ("세종대학교", 1446.0),
    ("단국대학교", 1434.0),
    ("한국항공대학교", 1422.0),
    ("서울과학기술대학교", 1410.0),
    ("숙명여자대학교", 1398.0),
    ("연세대학교 미래캠퍼스", 1374.0),

    # 광명상가 + 주요 수도권
    ("광운대학교", 1350.0),
    ("명지대학교", 1338.0),
    ("상명대학교", 1326.0),
    ("고려대학교 세종캠퍼스", 1320.0),
    ("가톨릭대학교", 1314.0),
    ("가천대학교", 1302.0),
    ("동국대학교 WISE캠퍼스", 1296.0),
    ("인천대학교", 1290.0),
    ("경기대학교", 1266.0),
    ("건국대학교 글로컬캠퍼스", 1248.0),
]


def normalize_name(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[\s()·._-]+", "", value)
    return value


_BASELINE_MAP = {normalize_name(name): rating for name, rating in OVERALL_BASELINE}


BRANCH_CAMPUS_PENALTY = 140.0
BRANCH_CAMPUS_FLOOR = 1080.0


def _looks_like_branch_campus(name: str) -> bool:
    value = (name or "").strip()
    upper = value.upper()
    return (
        "캠퍼스" in value
        or "교정" in value
        or "ERICA" in upper
        or "WISE" in upper
        or "글로컬" in value
        or bool(re.search(r"\((?:미래|세종|글로컬|ERICA|WISE|천안|죽전|글로벌)\)", value, re.I))
    )


def baseline_rating_for_name(name: str, board_slug: str = "overall") -> float:
    """Return the transparent initial prior for a university name.

    분교/이원화 캠퍼스도 랭킹에 남기되, 정확한 캠퍼스 시드가 없을 때는
    본교 시드보다 일정 점수를 낮춰 시작한다.
    """
    if board_slug != "overall":
        return 1500.0

    key = normalize_name(name)
    exact = _BASELINE_MAP.get(key)
    if exact is not None:
        return exact

    # 분교/이원화 캠퍼스는 본교와 동점으로 시작하지 않는다.
    if _looks_like_branch_campus(name):
        candidates = []
        for seed_name, rating in OVERALL_BASELINE:
            seed_key = normalize_name(seed_name)
            if key.startswith(seed_key) and key != seed_key:
                candidates.append((len(seed_key), rating))
        if candidates:
            _length, base_rating = max(candidates, key=lambda item: item[0])
            return max(BRANCH_CAMPUS_FLOOR, base_rating - BRANCH_CAMPUS_PENALTY)

    # 본교 이름의 표기 차이만 허용하는 보수적인 fallback.
    for seed_name, rating in OVERALL_BASELINE:
        seed_key = normalize_name(seed_name)
        if key == seed_key:
            return rating

    return DEFAULT_BASE_RATING


def baseline_defaults(board, university) -> dict:
    rating = baseline_rating_for_name(university.name, getattr(board, "slug", ""))
    return {
        "rating": rating,
        "rating_deviation": SEEDED_RD if rating != DEFAULT_BASE_RATING else DEFAULT_BASE_RD,
        "volatility": 0.06,
        "match_count": 0,
        "win_count": 0,
        "loss_count": 0,
    }


# 분교·이원화 캠퍼스도 VS/랭킹 후보에 남긴다. 단순 중복 캠퍼스는
# universities 정규화 단계에서 본교 University로 통합한다.
def is_ranking_eligible_name(name: str) -> bool:
    return bool((name or "").strip())


def ranking_university_queryset():
    from universities.models import University

    return University.objects.filter(is_active=True)


# Synthetic baseline exposure count used only for presentation. It is NOT written to
# ComparisonVote or UniversityRating.match_count and therefore never masquerades as
# real user participation. The UI labels it as "시드 포함".
def seed_sample_count_for_name(name: str, board_slug: str = "overall") -> int:
    if board_slug != "overall":
        return 0

    key = normalize_name(name)
    rank = None
    for index, (seed_name, _rating) in enumerate(OVERALL_BASELINE, start=1):
        if normalize_name(seed_name) == key:
            rank = index
            break

    checksum = sum((i + 1) * ord(ch) for i, ch in enumerate(key))
    jitter = checksum % 17
    if rank is not None:
        # Top schools receive a larger prior sample, tapering toward the lower seed list.
        return max(64, 238 - rank * 4 + jitter)
    return 42 + (checksum % 39)


def display_match_count_for_rating(rating_obj) -> int:
    board_slug = getattr(getattr(rating_obj, "board", None), "slug", "overall")
    seed_count = seed_sample_count_for_name(rating_obj.university.name, board_slug)
    return seed_count + int(getattr(rating_obj, "match_count", 0) or 0)
