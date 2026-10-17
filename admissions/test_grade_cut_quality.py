from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from universities.models import University

from .models import AdmissionAggregate, AdmissionMetric, AdmissionResult, AdmissionSource, RecruitmentUnit
from .services.grade_cut_quality import (
    double_one_cut_result_ids,
    without_invalid_double_one_results,
)


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ExactDoubleOneCutQualityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = University.objects.create(name="새빛대학교", region="서울")
        cls.source = AdmissionSource.objects.create(
            university=cls.school, admission_year=2026,
            source_type="ADIGA", source_url="https://example.com/grades",
        )

    def add_result(self, unit_name, cut50=None, cut70=None, *, college="", year=2026):
        unit = RecruitmentUnit.objects.create(
            university=self.school, name=unit_name, college_name=college,
        )
        source = self.source
        if year != source.admission_year:
            source = AdmissionSource.objects.create(
                university=self.school, admission_year=year,
                source_type="ADIGA", source_url="https://example.com/grades-other",
            )
        result = AdmissionResult.objects.create(
            university=self.school, recruitment_unit=unit, source=source,
            admission_year=year, admission_phase="SUSI",
            selection_category="학생부교과", selection_name="일반전형",
            recruitment_count=10,
        )
        for code, value in (
            ("STUDENT_GRADE_50_CUT", cut50),
            ("STUDENT_GRADE_70_CUT", cut70),
        ):
            if value is not None:
                AdmissionMetric.objects.create(
                    result=result, metric_code=code, unit="등급", value=Decimal(value),
                )
        return result

    def test_both_exact_one_only_not_either_or_university_wide(self):
        removed = self.add_result("데이터오류학과", "1", "1.00")
        valid_later = self.add_result("컴퓨터공학과", "1.00", "1.20")
        valid_earlier = self.add_result("정보보호학과", "1.10", "1.0")
        only_one = self.add_result("데이터과학과", "1", None)
        next_year = self.add_result("별도연도학과", "1.0", "1.0", year=2025)

        suspect = set(double_one_cut_result_ids().values_list("result_id", flat=True))
        self.assertEqual(suspect, {removed.pk, next_year.pk})
        valid = set(without_invalid_double_one_results(AdmissionResult.objects).values_list("pk", flat=True))
        self.assertEqual(valid, {valid_later.pk, valid_earlier.pk, only_one.pk})

    def test_protect_five_professional_majors_and_not_broad_health_fields(self):
        for name in (
            "의예과", "의학과", "치의예과", "치의학과",
            "한의예과", "한의학과", "약학과", "약학부",
            "수의예과", "수의학과",
        ):
            with self.subTest(name=name):
                item = self.add_result(name, "1", "1")
                self.assertNotIn(item.pk, set(double_one_cut_result_ids().values_list("result_id", flat=True)))
        college_protected = self.add_result(
            "통합학부", "1", "1", college="수의과대학",
        )
        for not_med in ("의공학과", "치위생학과", "간호학과", "제약공학과"):
            self.add_result(not_med, "1", "1")
        flagged = set(double_one_cut_result_ids().values_list("result_id", flat=True))
        self.assertNotIn(college_protected.pk, flagged)
        self.assertEqual(len(flagged), 4)

    def test_public_home_compare_and_unit_detail_hide_bad_row_but_keep_valid(self):
        bad = self.add_result("오류학부", "1.0", "1.0")
        good = self.add_result("신뢰학과", "1", "2.0")
        for params in ({}, {"metrics": "all"}):
            response = self.client.get(reverse("home"), params)
            self.assertNotIn(bad.pk, [x.pk for x in response.context["recent_results"]])
            self.assertIn(good.pk, [x.pk for x in response.context["recent_results"]])
        compare = self.client.get(reverse("admissions:compare"), {
            "grade": "1.5", "scope": "all",
        })
        self.assertEqual(compare.context["filtered_count"], 1)
        self.assertEqual(compare.context["rows"][0]["result"].pk, good.pk)

        page = self.client.get(reverse("admissions:unit", args=[bad.recruitment_unit_id]))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["result_count"], 0)

        protected = self.add_result("약학과", "1.0", "1.0")
        compare_med = self.client.get(reverse("admissions:compare"), {
            "grade": "1.5", "scope": "all",
        })
        self.assertEqual(compare_med.context["filtered_count"], 2)
        self.assertIn(protected.pk, [x["result"].pk for x in compare_med.context["rows"]])

    def test_preview_is_read_only_and_apply_deletes_only_exact_pair(self):
        bad = self.add_result("정리대상학과", "1.0", "1.0")
        good = self.add_result("보존대상학과", "1.0", "1.01")
        protected = self.add_result("의예과", "1.00", "1.00")

        preview = StringIO()
        call_command("remove_invalid_double_one_cuts", stdout=preview)
        self.assertIn("1건", preview.getvalue())
        self.assertIn("미리보기 모드", preview.getvalue())
        self.assertTrue(AdmissionResult.objects.filter(pk=bad.pk).exists())

        applied = StringIO()
        call_command("remove_invalid_double_one_cuts", "--apply", stdout=applied)
        self.assertFalse(AdmissionResult.objects.filter(pk=bad.pk).exists())
        self.assertFalse(AdmissionMetric.objects.filter(result_id=bad.pk).exists())
        self.assertTrue(AdmissionResult.objects.filter(pk=good.pk).exists())
        self.assertTrue(AdmissionResult.objects.filter(pk=protected.pk).exists())

        aggregates = AdmissionAggregate.objects.filter(
            university=self.school, admission_phase="SUSI",
            metric_code="STUDENT_GRADE_70_CUT", selection_category="학생부교과",
        )
        self.assertEqual(aggregates.count(), 1)
        self.assertEqual(aggregates.first().sample_count, 2)
        self.assertEqual(aggregates.first().value, Decimal("1.005"))
        self.assertIn("정리 및 집계 재계산 완료", applied.getvalue())

    def test_year_restricts_cleanup_scope(self):
        first = self.add_result("이번학년도오류학과", "1", "1")
        old = self.add_result("전년도오류학과", "1", "1", year=2025)
        call_command("remove_invalid_double_one_cuts", "--year=2026", "--apply", stdout=StringIO())
        self.assertFalse(AdmissionResult.objects.filter(pk=first.pk).exists())
        self.assertTrue(AdmissionResult.objects.filter(pk=old.pk).exists())
