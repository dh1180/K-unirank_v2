from django.test import SimpleTestCase

from universities.services.university_normalizer import (
    canonical_university_name,
    normalize_address,
    normalize_region,
    normalize_university_name,
    ranking_university_name,
)


class UniversityNormalizerTests(SimpleTestCase):
    def test_dual_campuses_are_kept_separate(self):
        self.assertEqual(
            canonical_university_name("건국대학교(글로컬)"),
            "건국대학교 글로컬캠퍼스",
        )
        self.assertEqual(
            canonical_university_name("한양대학교(ERICA)"),
            "한양대학교 ERICA캠퍼스",
        )
        self.assertEqual(
            canonical_university_name("명지대학교 자연캠퍼스"),
            "명지대학교 자연캠퍼스",
        )

    def test_dankook_is_split_by_address(self):
        self.assertEqual(
            ranking_university_name(
                "단국대학교",
                campus_name="본교",
                address="경기도 용인시 수지구 죽전로 152",
            ),
            "단국대학교 죽전캠퍼스",
        )
        self.assertEqual(
            ranking_university_name(
                "단국대학교",
                campus_name="제2캠퍼스",
                address="충청남도 천안시 동남구 단대로 119",
            ),
            "단국대학교 천안캠퍼스",
        )

    def test_myongji_is_split_by_address(self):
        self.assertEqual(
            ranking_university_name(
                "명지대학교",
                address="서울특별시 서대문구 거북골로 34",
            ),
            "명지대학교 인문캠퍼스",
        )
        self.assertEqual(
            ranking_university_name(
                "명지대학교",
                address="경기도 용인시 처인구 명지로 116",
            ),
            "명지대학교 자연캠퍼스",
        )

    def test_polytechnic_campuses_are_kept(self):
        name = "한국폴리텍대학 서울정수캠퍼스"
        self.assertEqual(canonical_university_name(name), name)

    def test_only_actual_mergers_use_current_university_name(self):
        self.assertEqual(
            canonical_university_name("강릉원주대학교"),
            "강원대학교",
        )
        self.assertEqual(
            canonical_university_name("안동대학교"),
            "국립경국대학교",
        )

    def test_national_prefix_does_not_break_matching(self):
        self.assertEqual(
            normalize_university_name("국립강릉원주대학교"),
            normalize_university_name("강릉원주대학교"),
        )

    def test_region_names_are_consistent(self):
        self.assertEqual(normalize_region("강원도"), "강원특별자치도")
        self.assertEqual(normalize_region("전북"), "전북특별자치도")
        self.assertEqual(
            normalize_region(address="제주도 제주시 제주대학로 102"),
            "제주특별자치도",
        )

    def test_address_uses_current_province_name(self):
        self.assertEqual(
            normalize_address("강원도 춘천시 강원대학길 1"),
            "강원특별자치도 춘천시 강원대학길 1",
        )
