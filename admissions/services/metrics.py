METRIC_LABELS = {
    "STUDENT_GRADE_50_CUT": "학생부등급 50% 컷",
    "STUDENT_GRADE_70_CUT": "학생부등급 70% 컷",
    "STUDENT_GRADE_85_CUT": "학생부등급 85% 컷",
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
