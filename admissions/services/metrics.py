METRIC_LABELS = {
    "STUDENT_GRADE_50_CUT": "학생부등급 50% 컷",
    "STUDENT_GRADE_70_CUT": "학생부등급 70% 컷",
    "STUDENT_GRADE_85_CUT": "학생부등급 85% 컷",
    "STUDENT_GRADE_90_CUT": "학생부등급 90% 컷",
    "STUDENT_GRADE_AVG": "학생부등급 평균",
    "STUDENT_GRADE_STDDEV": "학생부등급 표준편차",
    "CONVERTED_SCORE_50_CUT": "대학 환산점수 50% 컷",
    "CONVERTED_SCORE_70_CUT": "대학 환산점수 70% 컷",
    "CSAT_CONVERTED_SCORE_50_CUT": "수능 환산점수 50% 컷",
    "CSAT_CONVERTED_SCORE_70_CUT": "수능 환산점수 70% 컷",
    "CSAT_KOREAN_PERCENTILE_50_CUT": "국어 백분위 50% 컷",
    "CSAT_KOREAN_PERCENTILE_70_CUT": "국어 백분위 70% 컷",
    "CSAT_MATH_PERCENTILE_50_CUT": "수학 백분위 50% 컷",
    "CSAT_MATH_PERCENTILE_70_CUT": "수학 백분위 70% 컷",
    "CSAT_INQUIRY_PERCENTILE_50_CUT": "탐구 백분위 50% 컷",
    "CSAT_INQUIRY_PERCENTILE_70_CUT": "탐구 백분위 70% 컷",
    "CSAT_INQUIRY1_PERCENTILE_50_CUT": "탐구1 백분위 50% 컷",
    "CSAT_INQUIRY1_PERCENTILE_70_CUT": "탐구1 백분위 70% 컷",
    "CSAT_INQUIRY2_PERCENTILE_50_CUT": "탐구2 백분위 50% 컷",
    "CSAT_INQUIRY2_PERCENTILE_70_CUT": "탐구2 백분위 70% 컷",
    "CSAT_ENGLISH_GRADE_50_CUT": "영어등급 50% 컷",
    "CSAT_ENGLISH_GRADE_70_CUT": "영어등급 70% 컷",
    "CSAT_KOREAN_HISTORY_GRADE_50_CUT": "한국사등급 50% 컷",
    "CSAT_KOREAN_HISTORY_GRADE_70_CUT": "한국사등급 70% 컷",
    "CSAT_PERCENTILE_MEAN_50_CUT": "공식 평균 백분위 50% 컷",
    "CSAT_PERCENTILE_MEAN_70_CUT": "공식 평균 백분위 70% 컷",
    "CSAT_GRADE_50_CUT": "평균 수능등급 50% 컷",
    "CSAT_GRADE_70_CUT": "평균 수능등급 70% 컷",
    "ESSAY_SCORE_70_CUT": "논술 70% 컷",
    "ESSAY_SCORE_90_CUT": "논술 90% 컷",

    # 전문대학포털은 4년제 ADIGA의 50/70% 컷이 아니라
    # 자체 '합격자평균 / 합격자최저' 형식으로 공개한다.
    "COLLEGE_CSAT_AVERAGE": "수능 합격자 평균",
    "COLLEGE_STUDENT_AVERAGE": "학생부 합격자 평균",
    "COLLEGE_CSAT_MINIMUM": "수능 합격자 최저",
    "COLLEGE_STUDENT_MINIMUM": "학생부 합격자 최저",
}


def metric_label(code):
    return METRIC_LABELS.get(code, code.replace("_", " "))


def metric_unit(code):
    if "PERCENTILE" in code:
        return "백분위"
    if "GRADE" in code:
        return "등급"
    if "SCORE" in code:
        return "점"
    return ""


# 모바일 결과 목록은 한 화면에 여러 모집단위를 빠르게 훑는 것이 목적이다.
# 상세 지표 전체를 반복하지 않고 전형 특성에 맞는 50/70% 컷 한 쌍만 우선한다.
_MOBILE_SUSI_PAIRS = [
    ("STUDENT_GRADE_50_CUT", "STUDENT_GRADE_70_CUT"),
    ("CONVERTED_SCORE_50_CUT", "CONVERTED_SCORE_70_CUT"),
]

_MOBILE_JEONGSI_PAIRS = [
    ("CSAT_PERCENTILE_MEAN_50_CUT", "CSAT_PERCENTILE_MEAN_70_CUT"),
    ("CSAT_CONVERTED_SCORE_50_CUT", "CSAT_CONVERTED_SCORE_70_CUT"),
    ("CSAT_GRADE_50_CUT", "CSAT_GRADE_70_CUT"),
]


def attach_mobile_cut_metrics(results):
    """각 AdmissionResult에 모바일 목록용 대표 컷 최대 2개를 붙인다.

    prefetch_related('metrics')가 적용된 결과를 넘기는 것을 전제로 하며 DB를 수정하지 않는다.
    수시는 학생부등급, 정시는 공식 평균 백분위를 가장 먼저 사용한다.
    """
    for result in results:
        metrics = list(result.metrics.all())
        metric_by_code = {metric.metric_code: metric for metric in metrics}
        pairs = (
            _MOBILE_JEONGSI_PAIRS
            if result.admission_phase == "JEONGSI"
            else _MOBILE_SUSI_PAIRS
        )

        selected = []
        for code_50, code_70 in pairs:
            pair = [
                metric_by_code[code]
                for code in (code_50, code_70)
                if code in metric_by_code
            ]
            if pair:
                selected = pair
                break

        # 논술처럼 50% 컷은 없고 70% 컷만 공개되는 경우에는 70% 값 하나라도 보여준다.
        if not selected and "ESSAY_SCORE_70_CUT" in metric_by_code:
            selected = [metric_by_code["ESSAY_SCORE_70_CUT"]]

        for metric in selected:
            if "50_CUT" in metric.metric_code:
                metric.mobile_cut_label = "50%"
            elif "70_CUT" in metric.metric_code:
                metric.mobile_cut_label = "70%"
            else:
                metric.mobile_cut_label = "컷"
            metric.mobile_unit = metric.unit or metric_unit(metric.metric_code)

        result.mobile_cut_metrics = selected[:2]

    return results
