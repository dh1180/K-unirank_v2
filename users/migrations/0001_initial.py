# Generated manually for K-unirank favorites.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("universities", "0002_remove_university_campus_name_and_more"),
        ("admissions", "0002_alter_admissionsource_source_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="FavoriteUniversity",
            fields=[
                ("favorite_university_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("university", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorited_by_users", to="universities.university")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorite_universities", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "favorite_universities"},
        ),
        migrations.CreateModel(
            name="FavoriteRecruitmentUnit",
            fields=[
                ("favorite_recruitment_unit_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recruitment_unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorited_by_users", to="admissions.recruitmentunit")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorite_recruitment_units", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "favorite_recruitment_units"},
        ),
        migrations.AddConstraint(
            model_name="favoriteuniversity",
            constraint=models.UniqueConstraint(fields=("user", "university"), name="uq_fav_uni_user"),
        ),
        migrations.AddIndex(
            model_name="favoriteuniversity",
            index=models.Index(fields=["user", "created_at"], name="fav_uni_user_created_idx"),
        ),
        migrations.AddIndex(
            model_name="favoriteuniversity",
            index=models.Index(fields=["university"], name="fav_uni_university_idx"),
        ),
        migrations.AddConstraint(
            model_name="favoriterecruitmentunit",
            constraint=models.UniqueConstraint(fields=("user", "recruitment_unit"), name="uq_fav_unit_user"),
        ),
        migrations.AddIndex(
            model_name="favoriterecruitmentunit",
            index=models.Index(fields=["user", "created_at"], name="fav_unit_user_created_idx"),
        ),
        migrations.AddIndex(
            model_name="favoriterecruitmentunit",
            index=models.Index(fields=["recruitment_unit"], name="fav_unit_recruit_idx"),
        ),
    ]
