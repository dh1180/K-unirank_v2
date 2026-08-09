from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admissions", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="admissionsource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("ADIGA", "대입정보포털 어디가"),
                    ("PROCOLLEGE", "전문대학포털"),
                    ("UNIVERSITY", "대학 입학처"),
                    ("OTHER", "기타"),
                ],
                max_length=20,
            ),
        ),
    ]
