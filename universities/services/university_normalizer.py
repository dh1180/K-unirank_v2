import re


EXCLUDED_UNIVERSITY_NAMES = {
    "LH토지주택대학교",
    "SPC식품과학대학",
}


def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value or value.lower() == "null":
        return None

    return value


def canonical_university_name(name):
    name = clean_text(name)

    if not name:
        return ""

    name = re.sub(r"\s+", " ", name).strip()

    # 한국폴리텍대학은 캠퍼스별 항목을 각각 별도 대학으로 유지한다.
    if name.startswith("한국폴리텍"):
        return name

    name = re.sub(
        r"\s+(?:제\d+)?[A-Za-z0-9가-힣·ㆍ\-]+(?:\s+[A-Za-z0-9가-힣·ㆍ\-]+)?캠퍼스$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+(성신|성의|성심)교정$",
        "",
        name,
    )

    return name.strip()


def normalize_university_name(name):
    name = canonical_university_name(name)

    if not name:
        return ""

    name = name.replace("대학교", "대")
    name = re.sub(r"\s+", "", name)
    name = re.sub(r"[()\[\]{}·ㆍ,._-]", "", name)

    return name.lower()


def campus_label_from_name(name, canonical_name):
    name = clean_text(name)

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
