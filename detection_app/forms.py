from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

class UploadMediaForm(forms.Form):
    image = forms.ImageField(
        label='Upload Image for Weapon Detection',
        required=False
    )
    video = forms.FileField(
        label='Upload Video for Weapon Detection',
        required=False,
        # help_text='Allowed formats: mp4, avi, mov'
    )

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")

        if password != confirm:
            raise forms.ValidationError("Passwords do not match!")
        return cleaned_data


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Email / Username")
    password = forms.CharField(widget=forms.PasswordInput)

class OTPForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        label="Enter OTP"
    )