import unicodedata

from django import forms

from universities.models import University

from .models import SupportPledge


class SupportPledgeForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = SupportPledge
        fields = ["university", "amount", "depositor_name"]
        labels = {
            "university": "응원할 대학교",
            "amount": "후원 예정 금액 (원)",
            "depositor_name": "은행 이체 시 사용할 입금자명",
        }
        widgets = {
            "university": forms.Select(attrs={"class": "support-input"}),
            "amount": forms.NumberInput(attrs={
                "class": "support-input", "min": 1000, "max": 1000000,
                "step": 1000, "value": 5000, "inputmode": "numeric",
            }),
            "depositor_name": forms.TextInput(attrs={
                "class": "support-input", "autocomplete": "off",
                "maxlength": 40, "placeholder": "실제 입금자명과 동일하게 입력",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active = University.objects.filter(is_active=True)
        self.fields["university"].queryset = active
        # Deterministic 가나다 order, regardless of the production DB collation.
        universities = sorted(
            active.only("university_id", "name"),
            key=lambda university: (
                unicodedata.normalize("NFKC", university.name).casefold(),
                university.pk,
            ),
        )
        self.fields["university"].choices = [
            ("", "대학교 선택"),
            *((university.pk, university.name) for university in universities),
        ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("신청을 처리할 수 없습니다.")
        return cleaned

    def clean_depositor_name(self):
        name = self.cleaned_data["depositor_name"].strip()
        if len(name) < 2:
            raise forms.ValidationError("입금자명을 2자 이상 입력해주세요.")
        return name
