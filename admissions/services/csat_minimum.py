import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


MAIN_SECTION_PATTERN = re.compile(
    r"(?:Q\s*\d*\.?\s*)?(20\d{2})\s*학년도\s*전형별\s*주요사항"
)
RESULT_SECTION_PATTERN = re.compile(
    r"(?:Q\s*\d*\.?\s*)?(20\d{2})\s*학년도\s*전형\s*결과"
)


@dataclass(frozen=True)
class ParsedCsatMinimumRule:
    admission_year: int
    selection_name: str = ""
    recruitment_unit_name: str = ""
    applied: bool | None = None
    requirement_text: str = ""


def compact(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(value):
    value = compact(value).lower()
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def _selection_key(value):
    value = compact(value)
    value = re.sub(
        r"^(?:학생부위주\s*)?(?:학생부)?(?:교과|종합)\s*",
        "",
        value,
    )
    value = re.sub(r"[()\[\]{}<>]", " ", value)
    value = value.replace("전형", " ")
    return _key(value)


def _unit_keys(value):
    parts = re.split(r"[,/·ㆍ]|\s+및\s+|\s*\+\s*", compact(value))
    keys = {_key(part) for part in parts if _key(part)}
    whole = _key(value)
    if whole:
        keys.add(whole)
    return keys


def extract_adiga_code(url):
    try:
        values = parse_qs(urlparse(url or "").query).get("unvCd", [])
    except (TypeError, ValueError):
        return ""

    for value in values:
        value = str(value or "").strip()
        if re.fullmatch(r"\d{7}", value):
            return value
    return ""


def _expand_table(table):
    matrix = []
    pending = {}

    for tr in table.find_all("tr"):
        row = []
        col = 0

        def fill_pending():
            nonlocal col
            while col in pending:
                text, remaining = pending[col]
                while len(row) <= col:
                    row.append("")
                row[col] = text
                if remaining <= 1:
                    del pending[col]
                else:
                    pending[col] = (text, remaining - 1)
                col += 1

        fill_pending()

        for cell in tr.find_all(["th", "td"], recursive=False):
            fill_pending()
            text = compact(cell.get_text(" ", strip=True))
            try:
                rowspan = max(1, int(cell.get("rowspan", 1)))
            except (TypeError, ValueError):
                rowspan = 1
            try:
                colspan = max(1, int(cell.get("colspan", 1)))
            except (TypeError, ValueError):
                colspan = 1

            for offset in range(colspan):
                target = col + offset
                while len(row) <= target:
                    row.append("")
                row[target] = text
                if rowspan > 1:
                    pending[target] = (text, rowspan - 1)
            col += colspan

        if any(compact(cell) for cell in row):
            matrix.append(row)

    width = max((len(row) for row in matrix), default=0)
    return [row + [""] * (width - len(row)) for row in matrix]


def _nearest_section(table):
    for node in table.find_all_previous(string=True):
        text = compact(node)
        if not text:
            continue

        result_match = RESULT_SECTION_PATTERN.search(text)
        if result_match:
            return "result", int(result_match.group(1))

        main_match = MAIN_SECTION_PATTERN.search(text)
        if main_match:
            return "main", int(main_match.group(1))

    return None


def _nearest_adiga_tab_code(table):
    """표가 속한 ADIGA 전형 탭 코드를 찾는다.

    현재 어디가 상세 화면의 tab_20/30은 수시 학생부종합/교과,
    tab_40은 수능위주(정시) 영역이다. DOM 구조가 없는 구형 페이지는
    None을 반환해 기존 보수적 텍스트 필터로 처리한다.
    """
    for node in [table, *table.parents]:
        if not getattr(node, "attrs", None):
            continue
        node_id = compact(node.get("id", ""))
        if not node_id:
            continue
        match = re.search(r"(?:^|[^0-9])tab[_-]?(\d+)(?:[^0-9]|$)", node_id, re.I)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                return None
    return None


def _looks_like_selection_name(value):
    text = compact(value)
    if not text or len(text) > 120:
        return False

    blocked = {
        "전형별 주요사항",
        "전형별 전형요소",
        "구분",
        "모집단위",
        "수능최저학력기준",
        "비고",
        "전형방법",
    }
    if _key(text) in {_key(item) for item in blocked}:
        return False

    return (
        "전형" in text
        or text.endswith("추천")
        or text.endswith("우수자")
    )


def _nearest_selection_heading(table):
    for node in table.find_all_previous(
        ["h1", "h2", "h3", "h4", "h5", "h6", "strong", "dt"]
    ):
        text = compact(node.get_text(" ", strip=True))
        if _looks_like_selection_name(text):
            return text
        if MAIN_SECTION_PATTERN.search(text) or RESULT_SECTION_PATTERN.search(text):
            break
    return ""


def _applied_from_text(value):
    text = _key(value)
    if not text:
        return None

    negative = any(
        token in text
        for token in (
            "미적용",
            "적용하지않",
            "최저학력기준없",
            "수능최저없",
        )
    )
    positive = any(
        token in text
        for token in (
            "적용",
            "등급합",
            "등급이내",
            "합이",
            "합4",
            "합5",
            "합6",
            "합7",
            "합8",
            "합9",
            "합10",
        )
    )
    exception = any(
        token in text
        for token in (
            "일부",
            "단",
            "제외",
            "한하여",
        )
    )

    if negative and positive and exception:
        return None
    if negative:
        return False
    if positive:
        return True
    return None


def _snippet(value):
    text = compact(value)
    if not text:
        return ""

    marker_match = re.search(
        r"<?\s*수능\s*최저\s*학력\s*기준\s*>?",
        text,
    )
    if marker_match:
        text = text[marker_match.start():]

    text = re.sub(
        r"^<?\s*수능\s*최저\s*학력\s*기준\s*>?\s*[:：-]?\s*",
        "수능최저학력기준 ",
        text,
    )

    for marker in (
        " 학생부 100%",
        " 학생부교과 100%",
        " 서류 100%",
        " 학교별 추천",
        " 접수방식",
        " 전형방법:",
        " 전형방법：",
        " 학생부 반영방법",
        " 다단계 전형",
    ):
        index = text.find(marker, 8)
        if index != -1:
            text = text[:index]
            break

    return compact(text)[:700]


def _rule(
    admission_year,
    selection_name="",
    recruitment_unit_name="",
    text="",
):
    selection_name = compact(selection_name)
    recruitment_unit_name = compact(recruitment_unit_name)
    if not selection_name and not recruitment_unit_name:
        return None

    text = _snippet(text)
    if not text:
        return None

    return ParsedCsatMinimumRule(
        admission_year=admission_year,
        selection_name=selection_name,
        recruitment_unit_name=recruitment_unit_name,
        applied=_applied_from_text(text),
        requirement_text=text,
    )


def parse_csat_minimum_rules(html, admission_year):
    """ADIGA Q1의 수능최저 문구를 전형/모집단위 단위로 보수적으로 추출한다.

    같은 ADIGA 화면에는 Q1(해당 학년도 전형별 주요사항)과 Q2(전년도 결과)가
    함께 있으므로, Q1이 정확히 admission_year와 일치하는 table만 사용한다.
    또한 현재 DOM에서 tab_40으로 식별되는 수능위주(정시) 표는 구조적으로
    제외한다. 전형이나 모집단위를 확실히 식별하지 못한 전역 문장은 저장하지 않는다.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    parsed = []

    for table in soup.find_all("table"):
        if _nearest_section(table) != ("main", admission_year):
            continue

        # 수능최저 수집 대상은 수시다. 전형명 텍스트가 잘려도 정시 탭 자체는
        # 확실히 식별할 수 있으므로 tab_40 전체를 먼저 제외한다.
        if _nearest_adiga_tab_code(table) == 40:
            continue

        matrix = _expand_table(table)
        if not matrix:
            continue

        # 모집단위 | 수능최저학력기준 형태의 표
        unit_header = None
        minimum_header = None
        header_row_index = None

        for row_index, row in enumerate(matrix[:6]):
            keys = [_key(cell) for cell in row]
            for index, key in enumerate(keys):
                if "모집단위" in key and unit_header is None:
                    unit_header = index
                if "수능최저학력기준" in key and minimum_header is None:
                    minimum_header = index
            if unit_header is not None and minimum_header is not None:
                header_row_index = row_index
                break

        if header_row_index is not None:
            selection_context = _nearest_selection_heading(table)
            for row in matrix[header_row_index + 1:]:
                if max(unit_header, minimum_header) >= len(row):
                    continue

                unit = compact(row[unit_header])
                condition = compact(row[minimum_header])
                if not unit or not condition:
                    continue
                if "모집단위" in _key(unit):
                    continue
                if "수능최저학력기준" in _key(condition):
                    continue

                rule = _rule(
                    admission_year,
                    selection_name=selection_context,
                    recruitment_unit_name=unit,
                    text=(
                        condition
                        if "수능최저" in _key(condition)
                        else f"수능최저학력기준 {condition}"
                    ),
                )
                if rule:
                    parsed.append(rule)

        # 전형별 특성처럼 전형명 | 설명 형태의 표
        for row in matrix:
            cells = [compact(cell) for cell in row]
            if not any(cells):
                continue

            if len(cells) >= 2 and _looks_like_selection_name(cells[0]):
                trailing = " ".join(cell for cell in cells[1:] if cell)
                if "수능최저" in _key(trailing):
                    rule = _rule(
                        admission_year,
                        selection_name=cells[0],
                        text=trailing,
                    )
                    if rule:
                        parsed.append(rule)

            # marker가 별도 셀로 분리된 경우
            for index, cell in enumerate(cells):
                if "수능최저" not in _key(cell):
                    continue

                selection_name = ""
                for candidate in reversed(cells[:index]):
                    if _looks_like_selection_name(candidate):
                        selection_name = candidate
                        break

                if selection_name:
                    rule = _rule(
                        admission_year,
                        selection_name=selection_name,
                        text=cell,
                    )
                    if rule:
                        parsed.append(rule)

    # 같은 전형/모집단위 키가 여러 번 나오면 숫자 기준이 포함된 더 구체적인
    # 공식 문구를 우선한다. 서로 다른 범위는 별도 키로 유지한다.
    grouped = {}
    for rule in parsed:
        key = (
            _selection_key(rule.selection_name),
            tuple(sorted(_unit_keys(rule.recruitment_unit_name))),
        )
        current = grouped.get(key)
        if current is None:
            grouped[key] = rule
            continue
        if current.requirement_text == rule.requirement_text:
            continue

        current_score = len(current.requirement_text) + (
            60 if re.search(r"\d", current.requirement_text) else 0
        )
        new_score = len(rule.requirement_text) + (
            60 if re.search(r"\d", rule.requirement_text) else 0
        )
        if new_score > current_score:
            grouped[key] = rule

    return list(grouped.values())


def match_csat_minimum_rule(result, rules):
    """한 AdmissionResult에 확실히 대응하는 수능최저 규칙만 반환한다.

    source_code가 있으면 같은 ADIGA 대학 코드끼리만 비교하고, 모집단위 규칙은
    정확한 모집단위 토큰 일치가 필수다. 전형명도 정확/부분 포함 관계가 아니면
    붙이지 않는다. 최고점 규칙이 서로 다른 문구로 동률이면 안전하게 미매칭한다.
    """
    result_selection_key = _selection_key(
        getattr(result, "selection_name", "")
    )
    result_unit_key = _key(
        getattr(
            getattr(result, "recruitment_unit", None),
            "name",
            "",
        )
    )
    result_code = extract_adiga_code(
        getattr(getattr(result, "source", None), "source_url", "")
    )

    candidates = []

    for rule in rules:
        source_code = getattr(rule, "source_code", "")
        if source_code and result_code and source_code != result_code:
            continue

        score = 0
        rule_unit_name = getattr(rule, "recruitment_unit_name", "")
        if rule_unit_name:
            if not result_unit_key or result_unit_key not in _unit_keys(rule_unit_name):
                continue
            score += 180

        rule_selection = getattr(rule, "selection_name", "")
        if rule_selection:
            rule_selection_key = _selection_key(rule_selection)
            if not result_selection_key or not rule_selection_key:
                continue

            if rule_selection_key == result_selection_key:
                score += 220
            elif (
                min(len(rule_selection_key), len(result_selection_key)) >= 4
                and (
                    rule_selection_key in result_selection_key
                    or result_selection_key in rule_selection_key
                )
            ):
                score += 120
            else:
                continue
        elif not rule_unit_name:
            continue

        if getattr(rule, "applied", None) is not None:
            score += 5

        candidates.append((score, rule))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score = candidates[0][0]
    best = [rule for score, rule in candidates if score == best_score]
    texts = {
        compact(getattr(rule, "requirement_text", ""))
        for rule in best
    }
    if len(texts) > 1:
        return None

    return best[0]


def format_csat_minimum_display(requirement, max_length=150):
    if requirement is None:
        return ""

    if getattr(requirement, "applied", None) is False:
        return "수능최저 없음"

    text = compact(getattr(requirement, "requirement_text", ""))
    text = re.sub(
        r"^수능최저학력기준\s*",
        "",
        text,
    ).strip(" :-")

    if not text:
        return (
            "수능최저 적용"
            if getattr(requirement, "applied", None)
            else "수능최저 확인"
        )

    label = f"수능최저 {text}"
    if len(label) > max_length:
        label = label[: max_length - 1].rstrip() + "…"
    return label