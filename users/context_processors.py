from .models import FavoriteRecruitmentUnit, FavoriteUniversity


def favorites(request):
    if not request.user.is_authenticated:
        return {
            "favorite_university_ids": set(),
            "favorite_recruitment_unit_ids": set(),
        }

    return {
        "favorite_university_ids": set(
            FavoriteUniversity.objects.filter(user=request.user).values_list(
                "university_id", flat=True
            )
        ),
        "favorite_recruitment_unit_ids": set(
            FavoriteRecruitmentUnit.objects.filter(user=request.user).values_list(
                "recruitment_unit_id", flat=True
            )
        ),
    }
