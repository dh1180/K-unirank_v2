import re
from dataclasses import replace

from .csat_minimum import ParsedCsatMinimumRule, compact


def _key(value):
    return re.sub(r"[^0-9a-z가-힣]", "", compact(value).lower())


_GENERIC_TARGETS = {
    "대학학과전형",
    "전형명",
    "구분",
    "산출방법",
    "반영비율",
    "일괄선발",
    "1단계",
    "2단계",
    "전형요소및반영비율",
    "지원자격",
    "계열모집단위전형별주요사항",
}

_DESCRIPTION_MARKERS = (
    "지원자격",
    "서류평가",
    "면접평가",
    "고등교육을",
    "입학사정관",
    "제출서류",
)

_NEGATIVE_MARKERS = (
    "미적용",
    "적용하지않",
    "수능최저없",
    "최저학력기준없",
    "해당없",
    "최저학력없",
)

_POSITIVE_MARKERS = (
    "수능최저적용",
    "최저학력기준적용",
    "수능최저있",
    "최저학력기준있",
    "수능최저반영",
    "최저학력기준반영",
)

_EXCEPTION_MARKERS = (
    "단",
    "제외",
    "일부",
    "한하여",
    "만적용",
    "만반영",
)


def _has_threshold(text):
    text = compact(text)
    key = _key(text)

    if re.search(r"\d+(?:\.\d+)?\s*등급", text):
        return True
    if re.search(r"(?:합|등급합)\s*\d+", text):
        return True
    if re.search(r"\d+\s*(?:개\s*)?영역[^.]{0,80}(?:합|등급)", text):
        return True
    if "등급이내" in key or "등급합" in key:
        return True
    return False


def _looks_like_target(value, *, allow_selection=False):
    text = compact(value)
    if not text:
        return False

    key = _key(text)
    if not key or key in _GENERIC_TARGETS:
        return False

    max_length = 140 if allow_selection else 180
    if len(text) > max_length:
        return False

    if any(marker in text for marker in _DESCRIPTION_MARKERS):
        return False

    # 전형명이 아니라 표의 설명/주석을 제목으로 잘못 잡은 경우.
    if text.startswith(("-", "※", "■", "①", "②", "③")):
        return False

    if allow_selection:
        # 이 수집기는 '수시 수능최저' 전용이다. Q1에는 정시/수능위주 표도
        # 함께 있으므로 그 전형 제목은 여기서 확실히 제외한다.
        if key.startswith("수능") or "수능위주" in key or "정시" in key:
            return False

        # 표 제목/열 이름이 전형명처럼 잡힌 경우를 제거한다.
        if (
            "전형요소" in key
            or "반영비율" in key
            or "수능최저" in key
            or "최저학력기준" in key
        ):
            return False

    return True


def _clean_negative_text(text):
    key = _key(text)
    has_exception = any(marker in key for marker in _EXCEPTION_MARKERS)
    if has_exception:
        return compact(text)[:700]
    return "수능최저학력기준 없음"


def normalize_safe_csat_minimum_rule(rule):
    """공식 Q1 파싱 결과 중 수시 수능최저로 확실한 규칙만 통과시킨다.

    ADIGA의 복잡한 표에서는 '지원자격', '1단계', 모집단위명 자체가
    수능최저 열처럼 확장되거나 정시/수능위주 표가 함께 잡힐 수 있다.
    사이트 신뢰성을 위해 애매한 행은 저장하지 않고, 명시적인 없음/적용
    문구나 구체적인 등급 기준만 보존한다.
    """
    if rule is None:
        return None

    selection_name = compact(getattr(rule, "selection_name", ""))
    unit_name = compact(getattr(rule, "recruitment_unit_name", ""))
    text = compact(getattr(rule, "requirement_text", ""))

    if selection_name and not _looks_like_target(selection_name, allow_selection=True):
        return None
    if unit_name and not _looks_like_target(unit_name):
        return None
    if not selection_name and not unit_name:
        return None

    body = re.sub(r"^수능최저학력기준\s*", "", text).strip(" :-")
    body_key = _key(body)
    if not body_key or body_key in _GENERIC_TARGETS:
        return None

    # 모집단위 이름을 그대로 '최저기준'으로 잘못 읽은 행을 제거한다.
    if unit_name and body_key == _key(unit_name):
        return None

    key = _key(text)
    negative = any(marker in key for marker in _NEGATIVE_MARKERS)
    positive = any(marker in key for marker in _POSITIVE_MARKERS)
    threshold = _has_threshold(text)
    has_exception = any(marker in key for marker in _EXCEPTION_MARKERS)

    # '일반전형 | 수능최저 적용 | 1단계 수능 100%'처럼 Q1 정시 표의
    # 평범한 전형명이 수시 규칙처럼 잡힌 경우를 보수적으로 제거한다.
    if re.search(r"수능\s*100\s*%", body) and not re.search(
        r"학생부\s*(?:교과|종합)",
        selection_name,
    ):
        return None

    # 설명문에 우연히 '수능최저'라는 제목만 붙은 경우는 버린다.
    if (
        any(marker in body for marker in _DESCRIPTION_MARKERS)
        and not negative
        and not positive
        and not threshold
    ):
        return None

    if not negative and not positive and not threshold:
        return None

    applied = getattr(rule, "applied", None)
    if negative and (threshold or positive) and has_exception:
        # '일반학과 없음, 단 간호학과 적용'처럼 범위가 섞인 공식 문구.
        applied = None
    elif negative:
        applied = False
    elif positive or threshold:
        applied = True

    cleaned_text = text[:700]
    if applied is False:
        cleaned_text = _clean_negative_text(text)

    return replace(
        rule,
        selection_name=selection_name,
        recruitment_unit_name=unit_name,
        applied=applied,
        requirement_text=cleaned_text,
    )
