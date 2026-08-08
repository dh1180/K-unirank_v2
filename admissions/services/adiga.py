import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from universities.services.university_normalizer import clean_text, normalize_address


@dataclass(frozen=True)
class AdigaUniversityEntry:
    code: str
    name: str = ""
    campus_label: str = ""


@dataclass(frozen=True)
class AdigaUniversityDetail:
    code: str
    name: str
    address: str = ""
    campus_label: str = ""


@dataclass
class ParsedAdmissionRow:
    recruitment_unit: str
    admission_phase: str
    selection_category: str
    selection_name: str
    recruitment_group: str = ""
    recruitment_count: int | None = None
    applicant_count: int | None = None
    registered_count: int | None = None
    competition_rate: Decimal | None = None
    metrics: dict[str, Decimal] = field(default_factory=dict)


UNIVERSITY_LABEL_PATTERN = re.compile(
    r"([가-힣A-Za-z0-9·ㆍ.()\-\s]+(?:대학교|대학)(?:\s*\([^)]*\))?)\s*(?:\[([^\]]+)\])?"
)
CODE_PATTERN = re.compile(r"(?<!\d)(\d{7})(?!\d)")
UNVCD_PATTERN = re.compile(r"(?:unvCd|unvcd|UNVCD)\s*(?:=|:|,|\()\s*['\"]?(\d{7})")
# 최신 ADIGA는 accordion 제목의 ``Q 2026학년도 전형 결과`` 외에도
# 실제 콘텐츠 안에 ``2026 학년도 전형 결과``를 별도 제목으로 둔다.
# Q를 필수로 두면 requests로 받은 정적 HTML에서 종합만 잡히고 교과/정시
# 결과표를 놓치는 대학이 있으므로 Q 접두사는 선택 사항으로 처리한다.
RESULT_SECTION_PATTERN = re.compile(
    r"(?:Q\s*\d*\.?\s*)?(20\d{2})\s*학년도\s*전형\s*결과"
)
MAIN_SECTION_PATTERN = re.compile(
    r"(?:Q\s*\d*\.?\s*)?(20\d{2})\s*학년도\s*전형별\s*주요사항"
)


def compact(value):
    value = clean_text(value)
    return re.sub(r"\s+", " ", value or "").strip()


def to_decimal(value):
    value = compact(value)
    if not value or value in {"-", "–", "—", "·"}:
        return None

    value = value.replace(",", "")
    value = re.sub(r"\s*:\s*1\s*$", "", value)
    value = value.replace("%", "")

    match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value)
    if not match:
        return None

    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def decimal_to_int(value):
    if value is None:
        return None

    try:
        if value == value.to_integral_value():
            return int(value)
    except (AttributeError, ValueError):
        pass
    return None


def parse_university_entries(html):
    """목록 페이지에서 ADIGA 대학 코드 후보를 추출한다.

    대학명은 목록 HTML 구조에 따라 잘못 붙을 수 있어서 참고값으로만 사용한다.
    실제 매칭은 상세 페이지의 대학명과 주소를 다시 확인한다.
    """
    soup = BeautifulSoup(html, "html.parser")
    entries = {}

    for tag in soup.find_all(True):
        codes = _explicit_codes_from_tag(tag)
        if not codes:
            continue

        name, campus_label = _nearby_university_label(tag)
        for code in codes:
            current = entries.get(code)
            candidate = AdigaUniversityEntry(code, name, campus_label)
            if current is None or (not current.name and candidate.name):
                entries[code] = candidate

    if entries:
        return sorted(entries.values(), key=lambda entry: entry.code)

    # ADIGA 목록 구조가 바뀌어 명시적인 unvCd 표기를 찾지 못한 경우에만 사용한다.
    # 이 경우에도 상세 페이지 검증을 통과한 코드만 실제 저장된다.
    for code in dict.fromkeys(CODE_PATTERN.findall(str(soup))):
        entries[code] = AdigaUniversityEntry(code=code)

    return sorted(entries.values(), key=lambda entry: entry.code)


def _explicit_codes_from_tag(tag):
    codes = set()

    href = tag.get("href")
    if href:
        try:
            query = parse_qs(urlparse(href).query)
            for value in query.get("unvCd", []):
                if re.fullmatch(r"\d{7}", value):
                    codes.add(value)
        except (TypeError, ValueError):
            pass

        codes.update(re.findall(r"[?&]unvCd=(\d{7})(?:&|$)", href))

    for key in ("data-unv-cd", "data-unvcd", "data-unv_cd"):
        value = tag.get(key)
        if value and re.fullmatch(r"\d{7}", str(value).strip()):
            codes.add(str(value).strip())

    for key in ("onclick", "onchange", "data-url", "data-href"):
        value = tag.get(key)
        if not value:
            continue
        text = str(value)
        codes.update(re.findall(r"[?&]unvCd=(\d{7})(?:&|['\"\s)]|$)", text))
        codes.update(UNVCD_PATTERN.findall(text))

        if "univ" in text.lower() or "unv" in text.lower():
            codes.update(CODE_PATTERN.findall(text))

    tag_name = (tag.get("name") or "").lower()
    tag_id = (tag.get("id") or "").lower()
    value = str(tag.get("value") or "").strip()
    if ("unv" in tag_name or "univ" in tag_name or "unv" in tag_id or "univ" in tag_id):
        if re.fullmatch(r"\d{7}", value):
            codes.add(value)

    return codes


def _nearby_university_label(tag):
    text_candidates = [compact(tag.get_text(" ", strip=True))]

    tag_id = tag.get("id")
    if tag_id:
        label = tag.find_parent().find("label", attrs={"for": tag_id}) if tag.find_parent() else None
        if label is None:
            label = tag.find_previous("label", attrs={"for": tag_id})
        if label:
            text_candidates.append(compact(label.get_text(" ", strip=True)))

    parent = tag.parent
    for _ in range(2):
        if parent is None:
            break
        text_candidates.append(compact(parent.get_text(" ", strip=True)))
        parent = parent.parent

    for text in text_candidates:
        if not text:
            continue
        match = UNIVERSITY_LABEL_PATTERN.search(text)
        if not match:
            continue
        name = compact(match.group(1))
        campus_label = compact(match.group(2) or "")
        if _looks_like_university_name(name):
            return name, campus_label

    return "", ""


def parse_university_detail(html, code=""):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = compact(heading.get_text(" ", strip=True))
        if _looks_like_university_name(text):
            candidates.append(text)

    if not candidates:
        for node in soup.find_all(string=True):
            text = compact(node)
            if _looks_like_university_name(text):
                candidates.append(text)
                if len(candidates) >= 4:
                    break

    if not candidates:
        return None

    name = candidates[0]
    address = extract_detail_address(soup)
    campus_label = ""

    explicit = re.search(r"\(([^)]+)\)\s*$", name)
    if explicit:
        campus_label = compact(explicit.group(1))

    return AdigaUniversityDetail(
        code=code,
        name=name,
        address=address or "",
        campus_label=campus_label,
    )


def _looks_like_university_name(value):
    value = compact(value)
    if not value or len(value) > 80:
        return False

    blocked = {
        "대학정보",
        "일반대학",
        "대학/학과/전형",
        "대학 모집인원 탭 바",
    }
    if value in blocked:
        return False

    return bool(
        re.fullmatch(
            r"[가-힣A-Za-z0-9·ㆍ.()\-\s]+(?:대학교|대학)(?:\s*\([^)]*\))?",
            value,
        )
    )


def extract_detail_address(soup):
    for node in soup.find_all(string=re.compile(r"주소")):
        for parent in [node.parent, node.parent.parent if node.parent else None]:
            if parent is None:
                continue
            text = compact(parent.get_text(" ", strip=True))
            match = re.search(r"주소\s*[:：]?\s*(.+?)(?=\s+(?:전화|팩스)\b|$)", text)
            if match:
                address = normalize_address(match.group(1))
                if address and len(address) >= 5:
                    return address

    text = compact(soup.get_text(" ", strip=True))
    match = re.search(r"주소\s*[:：]?\s*(.+?)(?=\s+(?:전화|팩스)\b)", text)
    if match:
        return normalize_address(match.group(1)) or ""

    return ""


def parse_admission_results(html, admission_year):
    soup = BeautifulSoup(html, "html.parser")
    parsed = []

    for table in soup.find_all("table"):
        matrix = _expand_table(table)
        if len(matrix) < 2:
            continue

        flat_preview = _header_key(" ".join(cell for row in matrix[:6] for cell in row))
        if "모집단위" not in flat_preview or "경쟁률" not in flat_preview:
            continue

        section = _nearest_admission_section(table)
        if section is not None:
            section_type, section_year = section
            if section_type != "result" or section_year != admission_year:
                continue

        data_start = _find_data_start(matrix)
        if data_start is None:
            continue

        header_rows = matrix[:data_start]
        columns = _build_column_descriptors(header_rows)
        indexes = _resolve_core_columns(columns)

        if indexes["unit"] is None:
            continue
        if indexes["recruitment_count"] is None and indexes["competition_rate"] is None:
            continue

        tab_metadata = _admission_tab_metadata(table, soup, admission_year)
        if tab_metadata is None:
            # 어디가 탭을 확실히 식별하지 못한 표는 임의 분류하지 않는다.
            continue

        phase, category = tab_metadata
        local_selection_name = _selection_name_from_result_block(table)
        selection_name = local_selection_name or _selection_name(header_rows, table)

        refined = _refine_admission_metadata(
            phase=phase,
            category=category,
            selection_name=selection_name,
            columns=columns,
            data_rows=matrix[data_start:],
            indexes=indexes,
        )
        if refined is None:
            continue
        phase, category = refined

        # 최신 ADIGA의 정시 요약표는 한 표 안에 일반전형/실기/지역전형이
        # 섞이는 대학이 있다. 이런 표에 로컬 제목이 없으면 Q1의 마지막
        # 전형명을 끌어와 모든 행에 잘못 붙이지 않는다.
        if phase == "JEONGSI" and local_selection_name is None:
            if _table_has_recruitment_group_rows(matrix[data_start:], indexes):
                selection_name = ""

        for row in matrix[data_start:]:
            item = _parse_result_row_by_headers(
                row=row,
                columns=columns,
                indexes=indexes,
                phase=phase,
                category=category,
                selection_name=selection_name,
            )
            if item:
                parsed.append(item)

    return _deduplicate_rows(parsed)


def _nearest_admission_section(table):
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


def _expand_table(table):
    matrix = []
    pending = {}

    for tr in table.find_all("tr"):
        row = []
        col = 0

        def fill_pending_until_free():
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

        fill_pending_until_free()

        cells = tr.find_all(["th", "td"], recursive=False)
        for cell in cells:
            fill_pending_until_free()
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

        if pending:
            max_col = max(pending)
            while col <= max_col:
                if col in pending:
                    text, remaining = pending[col]
                    while len(row) <= col:
                        row.append("")
                    row[col] = text
                    if remaining <= 1:
                        del pending[col]
                    else:
                        pending[col] = (text, remaining - 1)
                col += 1

        if any(compact(cell) for cell in row):
            matrix.append(row)

    width = max((len(row) for row in matrix), default=0)
    return [row + [""] * (width - len(row)) for row in matrix]


def _header_key(value):
    value = compact(value).lower()
    value = value.replace("％", "%")
    value = re.sub(r"\s+", "", value)
    value = value.replace("컷", "cut")
    value = value.replace("c.u.t", "cut")
    value = value.replace("7０%", "70%")
    value = re.sub(r"(?<!\d)7\s*0%", "70%", value)
    return value


def _find_data_start(rows):
    for index, row in enumerate(rows):
        if len(row) < 3:
            continue

        normalized = [_header_key(cell) for cell in row]
        numeric_count = sum(to_decimal(cell) is not None for cell in row)
        if numeric_count < 2:
            continue

        joined = "|".join(normalized)
        if any(
            marker in joined
            for marker in (
                "최초(a)",
                "이월(b)",
                "최종(a+b)",
                "최종등록자",
                "대학별환산",
                "과목별백분위",
                "학생부등급",
                "지원및등록현황",
            )
        ) and "모집단위" in joined:
            continue

        text_cells = [cell for cell in normalized if cell and to_decimal(cell) is None]
        if not text_cells:
            continue

        if all(_looks_like_header_label(cell) for cell in text_cells):
            continue

        return index

    return None


def _looks_like_header_label(value):
    key = _header_key(value)
    if not key:
        return True

    exact = {
        "구분",
        "단과대학",
        "모집단위",
        "모집인원",
        "지원인원",
        "경쟁률",
        "입학인원",
        "등록인원",
        "추합최종번호",
        "추합인원",
        "충원합격순위",
        "인원수",
        "실질경쟁률",
        "평균",
        "표준편차",
        "50%",
        "50%cut",
        "70%",
        "70%cut",
        "85%",
        "85%cut",
        "총점(학생부)",
        "총점(수능)",
        "평가에반영된교과목",
        "지원및등록현황",
        "등록기준",
        "최저기준통과",
        "입학자학생부등급",
        "백분위",
        "합격자평균",
        "국",
        "수",
        "탐1",
        "탐2",
        "영",
        "한",
        "확률과통계",
        "미적분",
        "기하",
    }
    if key in exact:
        return True

    return any(
        marker in key
        for marker in (
            "최종등록자",
            "학생부등급",
            "환산등급",
            "대학별환산",
            "환산점수",
            "과목별백분위",
            "최초(a)",
            "이월(b)",
            "최종(a+b)",
        )
    )


def _build_column_descriptors(header_rows):
    width = max((len(row) for row in header_rows), default=0)
    columns = []

    for col in range(width):
        path = []
        for row in header_rows:
            value = compact(row[col]) if col < len(row) else ""
            if not value:
                continue
            if not path or path[-1] != value:
                path.append(value)

        full = " | ".join(path)
        columns.append(
            {
                "index": col,
                "path": path,
                "full": full,
                "key": _header_key(full),
                "leaf": _header_key(path[-1] if path else ""),
            }
        )

    return columns


def _resolve_core_columns(columns):
    return {
        "unit": _best_column(columns, _score_unit_column),
        "group": _best_column(columns, _score_group_column),
        "recruitment_count": _best_column(columns, _score_recruitment_count_column),
        "applicant_count": _best_column(columns, _score_applicant_count_column),
        "registered_count": _best_column(columns, _score_registered_count_column),
        "competition_rate": _best_column(columns, _score_competition_column),
    }


def _best_column(columns, scorer):
    scored = []
    for column in columns:
        score = scorer(column)
        if score > 0:
            scored.append((score, -column["index"], column["index"]))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]


def _score_unit_column(column):
    key = column["key"]
    leaf = column["leaf"]
    if leaf == "모집단위":
        return 100
    if "모집단위" in leaf:
        return 90
    if "모집단위" in key:
        return 60
    return 0


def _score_group_column(column):
    leaf = column["leaf"]
    if leaf in {"구분", "군", "모집군", "모집시기"}:
        return 100
    if "모집군" in leaf:
        return 90
    return 0


def _score_recruitment_count_column(column):
    key = column["key"]
    leaf = column["leaf"]
    if any(blocked in key for blocked in ("지원인원", "등록인원", "입학인원", "충원", "추합")):
        return 0

    if "모집인원" in key and ("최종(a+b)" in leaf or leaf.startswith("최종")):
        return 120
    if leaf in {"모집인원", "모집인원수"}:
        return 110
    if "모집인원" in leaf:
        return 100
    if "모집인원" in key:
        return 70
    return 0


def _score_applicant_count_column(column):
    leaf = column["leaf"]
    if leaf in {"지원인원", "지원자수", "지원자"}:
        return 100
    if "지원인원" in leaf or "지원자수" in leaf:
        return 90
    return 0


def _score_registered_count_column(column):
    leaf = column["leaf"]
    if leaf in {"최종등록인원", "등록인원", "입학인원"}:
        return 100
    if "최종등록인원" in leaf:
        return 95
    if "등록인원" in leaf or "입학인원" in leaf:
        return 85
    return 0


def _score_competition_column(column):
    leaf = column["leaf"]
    if leaf == "경쟁률":
        return 100
    if "경쟁률" in leaf and "실질" not in leaf:
        return 90
    return 0


def _selection_name(header_rows, table):
    # ADIGA 최신 결과의 공통 구조에서는 tbAdmRes 안의 h5 제목이
    # 해당 표의 실제 전형명을 가장 정확하게 나타낸다.
    block_name = _selection_name_from_result_block(table)
    if block_name:
        return block_name

    table_name = _selection_name_from_table_headers(header_rows)
    if table_name:
        return table_name

    # 표 안에 전형명이 없는 정시 표처럼 외부 제목으로만 제공되는 경우에만
    # 표 바로 앞의 명시적 전형명을 fallback으로 사용한다.
    for node in table.find_all_previous(string=True):
        value = compact(node)
        if not value or len(value) > 140:
            continue

        selection_bracket = re.search(r"\[([^\]]*전형[^\]]*)\]", value)
        if selection_bracket:
            candidate = _clean_selection_name(selection_bracket.group(1))
            if candidate:
                return candidate

        bracket = re.search(r"\[20\d{2}\s*학년도\s+([^\]]+)\]", value)
        if bracket:
            candidate = _clean_selection_name(bracket.group(1))
            if candidate:
                return candidate

        # 결과 표 영역을 벗어나면 더 위의 Q1 설명까지 탐색하지 않는다.
        if RESULT_SECTION_PATTERN.search(value):
            break

        if "전형" in value and "결과" not in value and "평가" not in value:
            if not _is_section_heading(value):
                candidate = re.split(r"※|☞|→", value, maxsplit=1)[0]
                candidate = _clean_selection_name(candidate)
                if candidate:
                    return candidate

    return "전형명 미확인"



def _selection_name_from_result_block(table):
    block = table.find_parent("div", class_="tbAdmRes")
    if block is None:
        return None

    # 한 tbAdmRes 안에 여러 제목/표가 들어가는 대학이 있으므로
    # block.find(...)로 첫 제목을 잡으면 뒤쪽 정시 표에 앞쪽 수시 제목이
    # 붙을 수 있다. 현재 table 바로 앞에 있는 가장 가까운 제목만 사용한다.
    title = None
    for node in block.descendants:
        if node is table:
            break

        name = getattr(node, "name", None)
        if name not in {"h3", "h4", "h5", "h6", "strong"}:
            continue

        # 표 내부의 strong/th 텍스트를 제목으로 오인하지 않는다.
        if node.find_parent("table") is not None:
            continue

        value = compact(node.get_text(" ", strip=True))
        if not value or len(value) > 180:
            continue

        key = _header_key(value)
        if (
            "전형" in value
            or key.startswith("수능")
            or "학생부종합" in key
            or "학생부교과" in key
        ):
            title = node

    if title is None:
        return None

    value = compact(title.get_text(" ", strip=True))
    if not value:
        return None

    # 학생부교과[교과우수자(추천형)전형] -> 교과우수자(추천형)전형
    bracket = re.search(r"\[([^\]]*전형[^\]]*)\]\s*$", value)
    if bracket:
        candidate = compact(bracket.group(1))
        if candidate:
            return candidate

    # 학생부 종합 (미래인재 전형) -> 미래인재 전형
    # 수능(일반전형) -> 일반전형
    match = re.search(r"\(([^()]*(?:전형|특별전형)[^()]*)\)\s*$", value)
    if match:
        candidate = compact(match.group(1))
        if candidate:
            return candidate

    candidate = _clean_selection_name(value)
    if candidate:
        key = _header_key(candidate)
        blocked = {
            "학생부",
            "학생부종합",
            "학생부교과",
            "백분위50%",
            "백분위70%",
            "대학별환산",
        }
        if key not in blocked:
            return candidate

    return None


def _selection_name_from_table_headers(header_rows):
    # 가장 신뢰도 높은 경우: 병합 헤더에 전형명이 직접 들어 있음.
    # 예) 모집단위 | 미래인재전형
    #     모집단위 | 고른기회전형
    explicit = []

    for row in header_rows[:8]:
        for cell in row:
            value = compact(cell)
            if not value:
                continue

            key = _header_key(value)

            if "전형" not in value:
                continue
            if _looks_like_header_label(value):
                continue
            if _is_section_heading(value):
                continue
            if "전형결과" in key or "전형별" in key or "전형방법" in key:
                continue
            if "학생부종합전형" == key or "학생부교과전형" == key:
                continue
            if "수능위주전형" == key or "수능전형" == key:
                continue

            candidate = _clean_selection_name(value)
            if candidate:
                explicit.append(candidate)

    if explicit:
        counts = {}
        order = []
        for candidate in explicit:
            if candidate not in counts:
                order.append(candidate)
                counts[candidate] = 0
            counts[candidate] += 1

        # 병합셀은 colspan 때문에 같은 전형명이 반복되므로 가장 많이
        # 반복된 값을 사용한다. 동률이면 표에서 먼저 나온 값을 사용한다.
        return max(order, key=lambda item: counts[item])

    # 전형명에 '전형'이라는 단어가 없는 대학을 위한 보조 처리.
    # 모집단위가 있는 헤더 행에서 일반 헤더명이 아닌 텍스트를 찾는다.
    for row in header_rows[:5]:
        keys = [_header_key(cell) for cell in row]
        if not any("모집단위" in key for key in keys):
            continue

        candidates = []
        for cell in row:
            value = compact(cell)
            key = _header_key(value)

            if not value or _looks_like_header_label(value):
                continue
            if re.fullmatch(r"\[?20\d{2}학년도.*\]?", key):
                continue
            if _is_section_heading(value):
                continue

            candidate = _clean_selection_name(value)
            if candidate:
                candidates.append(candidate)

        if candidates:
            counts = {}
            order = []
            for candidate in candidates:
                if candidate not in counts:
                    order.append(candidate)
                    counts[candidate] = 0
                counts[candidate] += 1
            return max(order, key=lambda item: counts[item])

    return None


def _clean_selection_name(value):
    value = compact(value)
    if not value:
        return None

    value = re.sub(r"^[◇◆□■○●▷▶·*\-]+\s*", "", value).strip()
    value = re.sub(r"^\[|\]$", "", value).strip()

    key = _header_key(value)
    if not value:
        return None
    if "학년도" in key:
        return None
    if "전형결과" in key or "전형별주요사항" in key:
        return None
    if value in {"학생부종합전형", "학생부교과전형", "수능위주전형", "수능전형"}:
        return None

    return value


def _is_section_heading(text):
    key = _header_key(text)
    return any(
        marker in key
        for marker in (
            "[수시]학생부종합전형",
            "[수시]학생부교과전형",
            "[정시]수능위주전형",
            "학생부종합전형",
            "학생부교과전형",
            "수능위주전형",
        )
    ) and len(key) <= 40


ADMISSION_TAB_METADATA = {
    "20": ("SUSI", "학생부종합"),
    "30": ("SUSI", "학생부교과"),
    "40": ("JEONGSI", "수능"),
}

ADMISSION_SECTION_METADATA = {
    "Ⅱ": ("SUSI", "학생부종합"),
    "II": ("SUSI", "학생부종합"),
    "Ⅲ": ("SUSI", "학생부교과"),
    "III": ("SUSI", "학생부교과"),
    "Ⅳ": ("JEONGSI", "수능"),
    "IV": ("JEONGSI", "수능"),
}


def _admission_tab_metadata(table, soup, admission_year):
    """어디가 탭 구조만으로 전형 유형을 결정한다.

    Ⅱ 학생부종합전형, Ⅲ 학생부교과전형, Ⅳ 수능위주전형이
    source of truth다. 대학별 전형명이나 표 안의 숫자로 유형을 추측하지 않는다.

    대학마다 탭 콘텐츠 DOM 구조가 조금씩 달라서 다음 순서로 탭을 찾는다.
    1. table 상위 DOM의 tab_20 / tab_30 / tab_40 계열 식별자
    2. table 앞의 명시적인 Ⅱ / Ⅲ / Ⅳ 섹션 제목
    3. 각 탭 안의 Q1 '전형별 주요사항' 영역 순서
    4. 각 탭 안의 Q2 '전형 결과' 영역 순서
    """
    metadata = _tab_metadata_from_ancestors(table)
    if metadata is not None:
        return metadata

    metadata = _tab_metadata_from_main_section_order(table, soup)
    if metadata is not None:
        return metadata

    metadata = _tab_metadata_from_result_section_order(
        table,
        soup,
        admission_year,
    )
    if metadata is not None:
        return metadata

    metadata = _tab_metadata_from_section_heading(table)
    if metadata is not None:
        return metadata

    return None



TAB_ORDER_METADATA = (
    ("SUSI", "학생부종합"),
    ("SUSI", "학생부교과"),
    ("JEONGSI", "수능"),
)


def _tab_metadata_from_main_section_order(table, soup):
    """탭 내부 Q1 영역의 문서 순서를 이용한다.

    어디가 UI의 콘텐츠 순서는 항상
    학생부종합 → 학생부교과 → 수능위주다.

    일부 대학은 콘텐츠 pane에 tab_20/30/40 id나 Ⅱ/Ⅲ/Ⅳ 텍스트를
    반복하지 않으므로, 각 탭에 하나씩 존재하는
    'Q 1. YYYY학년도 전형별 주요사항'을 탭 경계로 사용한다.
    """
    anchors = _main_section_anchors(soup)
    if len(anchors) != 3:
        return None

    nearest = _nearest_previous_anchor(table, MAIN_SECTION_PATTERN)
    if nearest is None:
        return None

    nearest_id = id(nearest)
    for index, anchor in enumerate(anchors):
        if id(anchor) == nearest_id:
            return TAB_ORDER_METADATA[index]

    return None


def _tab_metadata_from_result_section_order(table, soup, admission_year):
    """Q1 구조를 사용할 수 없을 때 Q2 결과 영역의 순서를 이용한다."""
    anchors = _result_section_anchors(soup, admission_year)
    if len(anchors) != 3:
        return None

    nearest = _nearest_previous_result_anchor(table, admission_year)
    if nearest is None:
        return None

    nearest_id = id(nearest)
    for index, anchor in enumerate(anchors):
        if id(anchor) == nearest_id:
            return TAB_ORDER_METADATA[index]

    return None


def _main_section_anchors(soup):
    anchors = []
    seen_parent_ids = set()

    for node in soup.find_all(string=True):
        value = compact(node)
        if not value or not MAIN_SECTION_PATTERN.search(value):
            continue

        # 같은 제목이 중첩 태그 때문에 중복 노출되는 경우를 줄인다.
        parent_id = id(getattr(node, "parent", None))
        if parent_id in seen_parent_ids:
            continue

        seen_parent_ids.add(parent_id)
        anchors.append(node)

    return anchors


def _result_section_anchors(soup, admission_year):
    anchors = []
    seen_parent_ids = set()

    for node in soup.find_all(string=True):
        value = compact(node)
        if not value:
            continue

        match = RESULT_SECTION_PATTERN.search(value)
        if not match or int(match.group(1)) != admission_year:
            continue

        parent_id = id(getattr(node, "parent", None))
        if parent_id in seen_parent_ids:
            continue

        seen_parent_ids.add(parent_id)
        anchors.append(node)

    return anchors


def _nearest_previous_anchor(table, pattern):
    for node in table.find_all_previous(string=True):
        value = compact(node)
        if value and pattern.search(value):
            return node
    return None


def _nearest_previous_result_anchor(table, admission_year):
    for node in table.find_all_previous(string=True):
        value = compact(node)
        if not value:
            continue

        match = RESULT_SECTION_PATTERN.search(value)
        if match and int(match.group(1)) == admission_year:
            return node

    return None


def _tab_metadata_from_ancestors(table):
    node = table

    while node is not None:
        values = []

        for attr in (
            "data-kunirank-tab-code",
            "id",
            "data-tab",
            "data-tab-id",
            "data-tab-target",
            "aria-labelledby",
            "data-target",
            "class",
        ):
            value = node.get(attr) if hasattr(node, "get") else None
            if not value:
                continue
            if isinstance(value, (list, tuple)):
                values.extend(str(item) for item in value)
            else:
                values.append(str(value))

        for value in values:
            metadata = _metadata_from_tab_attribute(value)
            if metadata is not None:
                return metadata

        node = getattr(node, "parent", None)

    return None


def _metadata_from_tab_attribute(value):
    value = compact(value).lower()
    if not value:
        return None

    # Selenium 상세 팝업 수집기가 명시적으로 붙이는 tab code.
    # 이 값은 실제 사용자가 클릭한 ADIGA 탭(20=종합, 30=교과, 40=수능)이다.
    if value in ADMISSION_TAB_METADATA:
        return ADMISSION_TAB_METADATA[value]

    patterns = (
        r"(?:^|[^0-9a-z])kunirank[_-]?tab[_-]?(20|30|40)(?:[^0-9]|$)",
        r"(?:^|[^0-9a-z])tab[_-]?(20|30|40)(?:[^0-9]|$)",
        r"(?:^|[^0-9a-z])tab(?:content|cont|panel|pane)[_-]?(20|30|40)(?:[^0-9]|$)",
        r"(?:^|[^0-9a-z])(?:content|cont|panel|pane)[_-]?tab[_-]?(20|30|40)(?:[^0-9]|$)",
    )

    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return ADMISSION_TAB_METADATA[match.group(1)]

    return None


def _tab_metadata_from_section_heading(table):
    """표 앞에서 가장 가까운 Ⅱ/Ⅲ/Ⅳ 탭 내부 섹션 제목을 찾는다."""
    for node in table.find_all_previous(string=True):
        text = compact(node)
        if not text or len(text) > 180:
            continue

        metadata = _metadata_from_section_heading(text)
        if metadata is not None:
            return metadata

    return None


def _metadata_from_section_heading(text):
    text = compact(text)
    if not text:
        return None

    # 실제 어디가 탭 내부 제목 예:
    # Ⅱ-1 『2026 학년도 전형별 주요사항』
    # Ⅲ-1 『2026 학년도 전형별 주요사항』
    # Ⅳ-1 『2026 학년도 전형별 주요사항』
    match = re.match(
        r"^\s*(Ⅳ|Ⅲ|Ⅱ|IV|III|II)\s*(?:[-–—.:]\s*\d+)?(?:\s|『|\[|$)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        prefix = match.group(1)
        if prefix in {"ii", "iii", "iv"}:
            prefix = prefix.upper()
        return ADMISSION_SECTION_METADATA.get(prefix)

    normalized = _header_key(text)

    # 2027 화면의 실제 콘텐츠에는 로마 숫자 탭 외에 아래 제목이 반복된다.
    #   2. 학생부종합전형 / 3. 학생부교과전형 / 4. 수능위주전형
    # 이 제목은 requests HTML에서도 안정적으로 존재하므로 가장 좋은 fallback이다.
    explicit_patterns = (
        (r"^(?:2[.\s-]*)?(?:\[수시\])?학생부종합전형$", ("SUSI", "학생부종합")),
        (r"^(?:3[.\s-]*)?(?:\[수시\])?학생부교과전형$", ("SUSI", "학생부교과")),
        (r"^(?:4[.\s-]*)?(?:\[정시\])?(?:수능위주전형|수능전형)$", ("JEONGSI", "수능")),
        (r"^(?:Ⅱ|II)[.\s-]*(?:\[수시\])?학생부종합전형$", ("SUSI", "학생부종합")),
        (r"^(?:Ⅲ|III)[.\s-]*(?:\[수시\])?학생부교과전형$", ("SUSI", "학생부교과")),
        (r"^(?:Ⅳ|IV)[.\s-]*(?:\[정시\])?(?:수능위주전형|수능전형)$", ("JEONGSI", "수능")),
    )

    for pattern, metadata in explicit_patterns:
        if re.fullmatch(pattern, normalized, flags=re.IGNORECASE):
            return metadata

    # 결과 블록 제목도 섹션 경계로 사용할 수 있다.
    # 전형명 내부에 '수능최저'가 들어가는 것만으로 정시로 보지 않도록
    # startswith/학생부 prefix처럼 강한 형태만 허용한다.
    if normalized.startswith("학생부교과[") or normalized.startswith("학생부교과("):
        return "SUSI", "학생부교과"
    if normalized.startswith("학생부종합[") or normalized.startswith("학생부종합("):
        return "SUSI", "학생부종합"
    if normalized.startswith("수능(") or normalized.startswith("수능["):
        return "JEONGSI", "수능"

    return None



def _parse_result_row_by_headers(row, columns, indexes, phase, category, selection_name):
    unit = _cell(row, indexes["unit"])
    if not unit or _is_non_unit_row(unit):
        return None

    recruitment_count = _int_cell(row, indexes["recruitment_count"])
    applicant_count = _int_cell(row, indexes["applicant_count"])
    registered_count = _int_cell(row, indexes["registered_count"])
    competition_rate = _decimal_cell(row, indexes["competition_rate"])

    if competition_rate is None and recruitment_count and applicant_count is not None:
        competition_rate = Decimal(applicant_count) / Decimal(recruitment_count)

    if competition_rate is not None and competition_rate < 0:
        competition_rate = None

    group_value = _cell(row, indexes["group"])
    group = _normalize_recruitment_group(group_value)
    row_selection_name = _selection_name_from_group(
        group_value,
        selection_name,
        phase=phase,
    )
    metrics = _extract_metrics(row, columns, phase)

    if recruitment_count is None and competition_rate is None and not metrics:
        return None

    return ParsedAdmissionRow(
        recruitment_unit=unit,
        admission_phase=phase,
        selection_category=category,
        selection_name=row_selection_name,
        recruitment_group=group,
        recruitment_count=recruitment_count,
        applicant_count=applicant_count,
        registered_count=registered_count,
        competition_rate=competition_rate,
        metrics=metrics,
    )


def _cell(row, index):
    if index is None or index >= len(row):
        return ""
    return compact(row[index])


def _decimal_cell(row, index):
    return to_decimal(_cell(row, index))


def _int_cell(row, index):
    return decimal_to_int(_decimal_cell(row, index))


def _is_non_unit_row(unit):
    key = _header_key(unit)
    if not key:
        return True
    if key in {"합계", "계", "전체", "총계", "소계"}:
        return True
    if "모집단위" in key:
        return True
    return False


def _selection_name_from_group(value, current, phase=""):
    if not value:
        return current

    cleaned = compact(value)
    match = re.match(
        r"^\s*(?:정시\s*)?([가나다])(?:\s*군)?(?:\s+|$)(.*)$",
        cleaned,
    )

    if not match:
        return current

    remainder = compact(match.group(2)).strip(" -/()")
    current_key = _header_key(current)

    if remainder and current_key in {"", "전형명미확인"}:
        return remainder

    # bare '가군/나군/다군'만으로 일반전형이라고 추측하지 않는다.
    # 같은 군 안에 실기/지역인재 등 다른 전형이 섞일 수 있기 때문이다.
    return current


def _normalize_recruitment_group(value):
    key = _header_key(value)
    if not key:
        return ""

    # '가군', '가군일반', '가', '정시(가)'를 모두 '가군'으로 정규화한다.
    match = re.match(r"^(?:정시)?\(?([가나다])\)?(?:군)?", key)
    if match:
        return f"{match.group(1)}군"

    return ""


def _extract_metrics(row, columns, phase):
    metrics = {}

    for column in columns:
        index = column["index"]
        value = _decimal_cell(row, index)
        if value is None:
            continue

        code = _metric_code_for_column(column, phase)
        if not code:
            continue

        value = _validate_metric_value(code, value)
        if value is not None:
            metrics[code] = value

    # 대학이 실제로 공개한 지표만 저장한다.
    # 국어·수학·탐구를 임의 평균한 K-unirank 참고 평균은 생성하지 않는다.
    return metrics


def _table_has_recruitment_group_rows(data_rows, indexes):
    group_index = indexes.get("group") if indexes else None
    if group_index is None:
        return False

    for row in data_rows or []:
        if _normalize_recruitment_group(_cell(row, group_index)):
            return True
    return False


def _refine_admission_metadata(
    phase,
    category,
    selection_name,
    columns,
    data_rows=None,
    indexes=None,
):
    """표 헤더와 전형명으로 *명백한* 오분류만 보정한다.

    원칙:
    - 실제 ADIGA 탭 분류(종합/교과/수능)를 우선한다.
    - `가군/나군/다군`이 있다는 이유만으로 수능으로 바꾸지 않는다.
    - 백분위/수능표준점수처럼 수능 결과임이 명백한 경우에만 정시로 보정한다.
    - 학생부 환산등급/교과성적 표가 정시로 잘못 감싸진 경우 전형명/기존 카테고리로
      종합·교과를 복구한다.
    """
    header_key = _header_key(
        " ".join(column.get("full", "") for column in columns)
    )
    name_key = _header_key(selection_name or "")

    has_student_result = any(
        marker in header_key
        for marker in (
            "학생부등급",
            "교과성적",
            "환산등급",
            "평가에반영된교과목",
        )
    )

    has_csat_result = any(
        marker in header_key
        for marker in (
            "백분위",
            "평균백분위",
            "수능표준점수",
            "총점(수능)",
            "수학선택과목",
            "과목별백분위",
        )
    ) or name_key.startswith("수능")

    # 명백한 수능 결과만 정시로 복구한다. 모집군 자체는 보조정보일 뿐이다.
    if phase != "JEONGSI" and has_csat_result and not has_student_result:
        return "JEONGSI", "수능"

    if phase == "JEONGSI" and has_student_result and not has_csat_result:
        if any(
            marker in name_key
            for marker in (
                "학생부교과",
                "교과우수자",
                "교과성적우수",
                "교과추천",
                "학교장추천",
                "추천형",
                "일반형",
            )
        ) or category == "학생부교과":
            return "SUSI", "학생부교과"

        if any(
            marker in name_key
            for marker in (
                "학교생활우수자",
                "학생부종합",
                "미래인재",
                "활동우수",
                "잠재능력",
                "서류형",
                "면접형",
                "강원인재",
                "사회통합",
                "글로벌인재",
                "농어촌",
                "특수교육",
            )
        ) or category == "학생부종합":
            return "SUSI", "학생부종합"

        return None

    return phase, category

def _metric_code_for_column(column, phase):
    key = column["key"]
    leaf = column["leaf"]
    cut = _cut_percent(key)

    # ADIGA 최신 상세결과 표는 교과 성적을
    #   학생부 > 환산점수 > 50% / 70%
    #   학생부 > 환산등급 > 50% / 70%
    # 처럼 별도 열로 제공한다.
    # 기존 코드는 "학생부등급"이라는 합쳐진 헤더만 인식해서
    # 최신 표의 "환산등급"을 누락했다.
    is_student_grade = phase != "JEONGSI" and (
        "학생부등급" in key
        or "입학자학생부등급" in key
        or ("학생부" in key and "교과성적" in key and "등급" in key)
        or "환산등급" in key
        or "대학별환산등급" in key
    )

    if is_student_grade:
        if cut in {50, 70, 85}:
            return f"STUDENT_GRADE_{cut}_CUT"
        if "표준편차" in leaf:
            return "STUDENT_GRADE_STDDEV"
        if leaf == "평균" or ("평균" in leaf and "수능" not in leaf and "백분위" not in leaf):
            return "STUDENT_GRADE_AVG"

    is_converted = "대학별환산" in key or "환산점수" in key
    if is_converted and cut in {50, 70}:
        prefix = "CSAT_CONVERTED_SCORE" if phase == "JEONGSI" else "CONVERTED_SCORE"
        return f"{prefix}_{cut}_CUT"

    if phase != "JEONGSI":
        return None

    if "평균" in key and "백분위" in key and cut in {50, 70}:
        return f"CSAT_PERCENTILE_MEAN_{cut}_CUT"

    if "평균수능등급" in key and cut in {50, 70}:
        return f"CSAT_GRADE_{cut}_CUT"

    subject = _csat_subject_for_column(key, column["leaf"])
    if subject and cut in {50, 70}:
        if subject in {"ENGLISH", "KOREAN_HISTORY"} and "등급" in key:
            return f"CSAT_{subject}_GRADE_{cut}_CUT"
        if subject in {"KOREAN", "MATH", "INQUIRY", "INQUIRY1", "INQUIRY2"} and "백분위" in key:
            return f"CSAT_{subject}_PERCENTILE_{cut}_CUT"

    return None


def _cut_percent(value):
    key = _header_key(value)
    for cut in (50, 70, 85):
        if re.search(rf"(?<!\d){cut}%(?:cut)?", key):
            return cut
    return None


def _csat_subject_for_column(key, leaf=""):
    leaf = _header_key(leaf)

    exact_leaf_map = {
        "국": "KOREAN",
        "국어": "KOREAN",
        "수": "MATH",
        "수학": "MATH",
        "탐": "INQUIRY",
        "탐구": "INQUIRY",
        "탐평": "INQUIRY",
        "탐구평균": "INQUIRY",
        "탐1": "INQUIRY1",
        "탐구1": "INQUIRY1",
        "탐①": "INQUIRY1",
        "탐구①": "INQUIRY1",
        "탐2": "INQUIRY2",
        "탐구2": "INQUIRY2",
        "탐②": "INQUIRY2",
        "탐구②": "INQUIRY2",
        "영": "ENGLISH",
        "영어": "ENGLISH",
        "한": "KOREAN_HISTORY",
        "한국사": "KOREAN_HISTORY",
    }
    if leaf in exact_leaf_map:
        return exact_leaf_map[leaf]

    if "국어" in leaf:
        return "KOREAN"
    if "수학" in leaf:
        return "MATH"
    if leaf in {"탐", "탐구", "탐평", "탐구평균"}:
        return "INQUIRY"
    if any(marker in leaf for marker in ("탐구1", "탐①", "탐구①", "탐(1)")):
        return "INQUIRY1"
    if any(marker in leaf for marker in ("탐구2", "탐②", "탐구②", "탐(2)")):
        return "INQUIRY2"
    if "영어" in leaf:
        return "ENGLISH"
    if "한국사" in leaf:
        return "KOREAN_HISTORY"

    if "국어" in key:
        return "KOREAN"
    if "수학" in key:
        return "MATH"
    if any(marker in key for marker in ("탐구1", "탐구①", "탐구(1)", "탐①")):
        return "INQUIRY1"
    if any(marker in key for marker in ("탐구2", "탐구②", "탐구(2)", "탐②")):
        return "INQUIRY2"
    if "영어" in key and "한국사" not in leaf:
        return "ENGLISH"
    if "한국사" in key:
        return "KOREAN_HISTORY"
    return None


def _validate_metric_value(code, value):
    if value is None:
        return None

    if "GRADE" in code:
        if Decimal("1") <= value <= Decimal("9"):
            return value
        return None

    if "PERCENTILE" in code:
        if Decimal("0") <= value <= Decimal("100"):
            return value
        return None

    return value


def _deduplicate_rows(rows):
    unique = {}

    for row in rows:
        key = (
            row.recruitment_unit,
            row.admission_phase,
            row.selection_category,
            row.selection_name,
            row.recruitment_group,
        )

        existing = unique.get(key)
        if existing is None:
            unique[key] = row
            continue

        existing_score = _row_quality_score(existing)
        candidate_score = _row_quality_score(row)
        if candidate_score > existing_score:
            unique[key] = row

    return list(unique.values())


def _row_quality_score(row):
    score = len(row.metrics) * 10
    score += 2 if row.recruitment_count is not None else 0
    score += 2 if row.competition_rate is not None else 0
    score += 1 if row.applicant_count is not None else 0
    score += 1 if row.registered_count is not None else 0
    return score



def has_result_section(html, admission_year):
    """해당 학년도 전형결과 제목이 원문 HTML에 존재하는지 확인한다."""
    soup = BeautifulSoup(html or "", "html.parser")
    text = compact(soup.get_text(" ", strip=True))

    for match in RESULT_SECTION_PATTERN.finditer(text):
        if int(match.group(1)) == int(admission_year):
            return True

    return False


def extract_result_year(html, fallback=None):
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    matches = re.findall(r"Q\s*\d*\.?\s*(20\d{2})\s*학년도\s*전형\s*결과", text)
    if matches:
        return int(matches[0])

    matches = re.findall(r"(20\d{2})\s*학년도\s*전형\s*결과", text)
    if matches:
        return int(matches[-1])

    return fallback
