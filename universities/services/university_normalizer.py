import re


EXCLUDED_UNIVERSITY_NAMES = {
    "LH토지주택대학교",
    "SPC식품과학대학",
    "정석대학",
    "정석대학교",
}

REGION_ALIASES = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "전남광주특별광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "강원도": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전라북도": "전북특별자치도",
    "광주광역시": "전남광주특별광역시",
    "전남": "전남광주특별광역시",
    "전라남도": "전남광주특별광역시",
    "전남광주통합특별시": "전남광주특별광역시",
    "전남광주특별광역시": "전남광주특별광역시",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
    "제주도": "제주특별자치도",
}

REGION_NAMES = (
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "광주광역시",
    "대전광역시",
    "울산광역시",
    "세종특별자치시",
    "경기도",
    "강원특별자치도",
    "강원도",
    "충청북도",
    "충청남도",
    "전북특별자치도",
    "전라북도",
    "전남광주특별광역시",
    "전남광주통합특별시",
    "전라남도",
    "경상북도",
    "경상남도",
    "제주특별자치도",
    "제주도",
)

# 실제로 하나의 대학으로 통합된 경우만 현재 교명으로 묶는다.
NAME_ALIASES = {
    "한국골프대학교": "한국골프과학기술대학교",
    "강릉원주대학교": "강원대학교",
    "국립강릉원주대학교": "강원대학교",
    "안동대학교": "국립경국대학교",
    "국립안동대학교": "국립경국대학교",
    "경북도립대학교": "국립경국대학교",
    "경남도립거창대학": "국립창원대학교",
    "경남도립거창대학교": "국립창원대학교",
    "경남도립남해대학": "국립창원대학교",
    "경남도립남해대학교": "국립창원대학교",
}

MERGED_UNIVERSITIES = {
    "강원대학교",
    "국립경국대학교",
    "국립창원대학교",
}

# 대학 단위 랭킹/입시 페이지를 별도로 만들 필요가 없는 캠퍼스들.
# 캠퍼스 자체 정보는 UniversityCampus에 남기고 University는 본교 하나로 묶는다.
COLLAPSED_CAMPUS_BASES = {
    "가톨릭대학교",
}

# 분교·이원화 캠퍼스는 본교와 합치지 않고 표시 이름만 통일한다.
EXPLICIT_CAMPUS_ALIASES = {
    "건국대학교(글로컬)": "건국대학교 글로컬캠퍼스",
    "건국대학교 (글로컬)": "건국대학교 글로컬캠퍼스",
    "고려대학교(세종)": "고려대학교 세종캠퍼스",
    "고려대학교 (세종)": "고려대학교 세종캠퍼스",
    "동국대학교(WISE)": "동국대학교 WISE캠퍼스",
    "동국대학교 (WISE)": "동국대학교 WISE캠퍼스",
    "연세대학교(미래)": "연세대학교 미래캠퍼스",
    "연세대학교 (미래)": "연세대학교 미래캠퍼스",
    "한양대학교(ERICA)": "한양대학교 ERICA캠퍼스",
    "한양대학교 (ERICA)": "한양대학교 ERICA캠퍼스",

    # ADIGA에서 캠퍼스별 code를 별도 운영하는 대학.
    # 대표 캠퍼스는 기존 대학명을 유지하고 비대표 캠퍼스만 suffix를 붙인다.
    "건양대학교 메디컬": "건양대학교 메디컬캠퍼스",
    "경기대학교 서울": "경기대학교 서울캠퍼스",
    "경동대학교 메디컬": "경동대학교 메디컬캠퍼스",
    "경동대학교 메트로폴": "경동대학교 메트로폴캠퍼스",
    "신한대학교 동두천": "신한대학교 동두천캠퍼스",
    "안양대학교 강화": "안양대학교 강화캠퍼스",
    "영산대학교 양산": "영산대학교 양산캠퍼스",
    "을지대학교 대전": "을지대학교 대전캠퍼스",
    "을지대학교 의정부": "을지대학교 의정부캠퍼스",
    "전남대학교 여수": "전남대학교 여수캠퍼스",
    "중앙대학교 안성": "중앙대학교 다빈치캠퍼스",
    "중앙대학교 다빈치": "중앙대학교 다빈치캠퍼스",
    "예원예술대학교 전북희망": "예원예술대학교 전북희망캠퍼스",
    "인천가톨릭대학교 강화": "인천가톨릭대학교 강화캠퍼스",

    # 상명대학교는 ADIGA에서 서울/천안을 서로 다른 unvCd로 관리한다.
    # 서비스에서는 서울은 기존 이름을 유지하고 천안만 별도 대학으로 표시한다.
    "상명대학교 본교": "상명대학교",
    "상명대학교(본교)": "상명대학교",
    "상명대학교 (본교)": "상명대학교",
    "상명대학교 서울캠퍼스": "상명대학교",
    "상명대학교(서울)": "상명대학교",
    "상명대학교 (서울)": "상명대학교",
    "상명대학교 제2캠퍼스": "상명대학교 천안캠퍼스",
    "상명대학교(제2캠퍼스)": "상명대학교 천안캠퍼스",
    "상명대학교 (제2캠퍼스)": "상명대학교 천안캠퍼스",
    "상명대학교(천안)": "상명대학교 천안캠퍼스",
    "상명대학교 (천안)": "상명대학교 천안캠퍼스",

    # 홍익대학교는 ADIGA/CareerNet에서 본교와 제2캠퍼스로 분리되어 있다.
    # 서비스에서는 실제 지역을 반영해 서울/세종캠퍼스로 표기한다.
    "홍익대학교 본교": "홍익대학교",
    "홍익대학교(본교)": "홍익대학교",
    "홍익대학교 (본교)": "홍익대학교",
    "홍익대학교 제2캠퍼스": "홍익대학교 세종캠퍼스",
    "홍익대학교(제2캠퍼스)": "홍익대학교 세종캠퍼스",
    "홍익대학교 (제2캠퍼스)": "홍익대학교 세종캠퍼스",
    "홍익대학교(세종)": "홍익대학교 세종캠퍼스",
    "홍익대학교 (세종)": "홍익대학교 세종캠퍼스",
}

ADDRESS_CAMPUS_RULES = {
    "단국대학교": (
        ("경기도 용인", "죽전캠퍼스"),
        ("충청남도 천안", "천안캠퍼스"),
    ),
    "명지대학교": (
        ("서울특별시", "인문캠퍼스"),
        ("경기도 용인", "자연캠퍼스"),
    ),
    # 아래 대학들은 ADIGA가 캠퍼스별 external code를 별도로 제공한다.
    # 대표 캠퍼스 주소는 기본 대학명을 유지하고, 비대표 캠퍼스 주소만 suffix를 붙인다.
    "건양대학교": (
        ("대전광역시", "메디컬캠퍼스"),
    ),
    "경기대학교": (
        ("서울특별시", "서울캠퍼스"),
    ),
    "경동대학교": (
        ("강원특별자치도 원주", "메디컬캠퍼스"),
        ("경기도 양주", "메트로폴캠퍼스"),
    ),
    "신한대학교": (
        ("경기도 동두천", "동두천캠퍼스"),
    ),
    "안양대학교": (
        ("인천광역시 강화", "강화캠퍼스"),
    ),
    "영산대학교": (
        ("경상남도 양산", "양산캠퍼스"),
    ),
    "을지대학교": (
        ("대전광역시", "대전캠퍼스"),
        ("경기도 의정부", "의정부캠퍼스"),
    ),
    "전남대학교": (
        ("전라남도 여수", "여수캠퍼스"),
    ),
    "중앙대학교": (
        ("경기도 안성", "다빈치캠퍼스"),
    ),
    "예원예술대학교": (
        ("전북특별자치도 임실", "전북희망캠퍼스"),
    ),
    "인천가톨릭대학교": (
        ("인천광역시 강화", "강화캠퍼스"),
    ),

    # 상명대 서울은 "상명대학교", 천안만 별도 대학으로 유지한다.
    "상명대학교": (
        ("충청남도 천안", "천안캠퍼스"),
    ),
    # ADIGA 기준 본교(서울) / 제2캠퍼스(세종)를 별도 대학 단위로 유지한다.
    # 서울은 기존 대표 이름 "홍익대학교"를 그대로 사용한다.
    "홍익대학교": (
        ("세종특별자치시", "세종캠퍼스"),
    ),
}

PRIMARY_CAMPUS_LABELS = {
    "",
    "본교",
    "본캠퍼스",
    "제1캠퍼스",
    "1캠퍼스",
}


def clean_text(value):
    if value is None:
        return None

    value = re.sub(r"\s+", " ", str(value)).strip()
    if not value or value.lower() == "null":
        return None
    return value


def normalize_address(value):
    value = clean_text(value)
    if not value:
        return None

    value = value.replace("강원도 ", "강원특별자치도 ")
    value = value.replace("전라북도 ", "전북특별자치도 ")
    value = value.replace("제주도 ", "제주특별자치도 ")
    value = value.replace("전남광주통합특별시 ", "전남광주특별광역시 ")
    return value


def normalize_region(value=None, address=None):
    value = clean_text(value)

    if value in REGION_ALIASES:
        return REGION_ALIASES[value]

    if value:
        for name in REGION_NAMES:
            if value == name or value.startswith(name):
                return REGION_ALIASES.get(name, name)

    address = normalize_address(address)
    if address:
        for name in REGION_NAMES:
            if address.startswith(name):
                return REGION_ALIASES.get(name, name)

    return value


def canonical_university_name(name):
    name = clean_text(name)
    if not name:
        return ""

    name = re.sub(r"\[(본교|분교|제\d+캠퍼스)\]$", "", name).strip()

    if name in NAME_ALIASES:
        return NAME_ALIASES[name]

    if name in EXPLICIT_CAMPUS_ALIASES:
        return EXPLICIT_CAMPUS_ALIASES[name]

    return name


def campus_name_from_address(base_name, address):
    address = normalize_address(address)
    if not address:
        return None

    for prefix, campus_name in ADDRESS_CAMPUS_RULES.get(base_name, ()):
        if address.startswith(prefix):
            return campus_name

    return None


def normalize_campus_label(value):
    value = clean_text(value)
    if not value:
        return ""

    value = value.strip("[]() ")

    if value in PRIMARY_CAMPUS_LABELS:
        return value

    if value.lower() == "glocal":
        return "글로컬캠퍼스"
    if value.upper() == "ERICA":
        return "ERICA캠퍼스"
    if value.upper() == "WISE":
        return "WISE캠퍼스"

    if value in {"글로컬", "세종", "미래", "인문", "자연", "죽전", "천안", "서울"}:
        return f"{value}캠퍼스"

    if value.endswith("캠퍼스") or value.endswith("교정"):
        return value

    return value


def city_campus_label(address):
    address = normalize_address(address)
    if not address:
        return None

    parts = address.split()
    if not parts:
        return None

    first = parts[0]
    if first in {
        "서울특별시", "부산광역시", "대구광역시", "인천광역시",
        "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
    }:
        city = first.replace("특별자치시", "").replace("특별시", "").replace("광역시", "")
        return f"{city}캠퍼스"

    if len(parts) >= 2:
        city = re.sub(r"(특별자치시|시|군)$", "", parts[1])
        if city:
            return f"{city}캠퍼스"

    return None


def ranking_university_name(name, campus_name=None, address=None):
    base_name = canonical_university_name(name)
    if not base_name:
        return ""

    if base_name in MERGED_UNIVERSITIES or base_name in COLLAPSED_CAMPUS_BASES:
        return base_name

    if base_name.startswith("한국폴리텍") and "캠퍼스" in base_name:
        return base_name

    explicit_campus = re.search(r"(?:\s|^)([^\s]+캠퍼스|[^\s]+교정)$", base_name)
    if explicit_campus:
        return base_name

    address_label = campus_name_from_address(base_name, address)
    if address_label:
        return f"{base_name} {address_label}"

    label = normalize_campus_label(campus_name)
    # 제2캠퍼스/2캠퍼스 같은 단순 번호 캠퍼스는 기본적으로 별도 대학으로 만들지 않는다.
    # 홍익대/상명대는 위 ADDRESS_CAMPUS_RULES에서 주소 기준으로 먼저 분리된다.
    if label and re.fullmatch(r"(?:제)?\d+캠퍼스", label):
        return base_name

    if label and label not in PRIMARY_CAMPUS_LABELS:
        return f"{base_name} {label}"

    return base_name


def fallback_split_name(name, campus_name=None, address=None):
    base_name = canonical_university_name(name)

    if base_name in COLLAPSED_CAMPUS_BASES:
        return base_name

    resolved = ranking_university_name(name, campus_name, address)

    if resolved != base_name:
        return resolved

    label = normalize_campus_label(campus_name)
    if label and re.fullmatch(r"(?:제)?\d+캠퍼스", label):
        return base_name

    if label and label not in PRIMARY_CAMPUS_LABELS:
        return f"{base_name} {label}"

    city_label = city_campus_label(address)
    if city_label:
        return f"{base_name} {city_label}"

    return base_name


def normalize_university_name(name):
    name = canonical_university_name(name)
    if not name:
        return ""

    name = re.sub(r"^국립(?=[가-힣A-Za-z])", "", name)
    name = name.replace("대학교", "대")
    name = re.sub(r"\s+", "", name)
    name = re.sub(r"[()\[\]{}·ㆍ,._-]", "", name)
    return name.lower()


def campus_label_from_name(name, canonical_name):
    name = clean_text(name)
    canonical_name = clean_text(canonical_name)

    if not name or not canonical_name or name == canonical_name:
        return None

    if name.startswith("한국폴리텍"):
        return None

    if name.startswith(canonical_name):
        suffix = name[len(canonical_name):].strip()
        if suffix:
            return suffix

    return None


def is_excluded_university(name, school_type=None):
    name = clean_text(name)
    school_type = clean_text(school_type)

    if name in EXCLUDED_UNIVERSITY_NAMES:
        return True

    if school_type and "사내대학" in school_type:
        return True

    return False
