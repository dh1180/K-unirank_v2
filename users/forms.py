from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="아이디",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "아이디를 입력하세요",
            }
        ),
    )
    password = forms.CharField(
        label="비밀번호",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "비밀번호를 입력하세요",
            }
        ),
    )


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        label="이메일",
        required=False,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "example@email.com",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
        labels = {"username": "아이디"}
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "autocomplete": "username",
                    "autofocus": True,
                    "placeholder": "사용할 아이디를 입력하세요",
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "비밀번호"
        self.fields["password2"].label = "비밀번호 확인"
        self.fields["password1"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "비밀번호를 입력하세요",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "비밀번호를 한 번 더 입력하세요",
            }
        )
