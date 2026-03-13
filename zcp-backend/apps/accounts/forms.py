from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    org_name = forms.CharField(max_length=255, label="Organization name")
    slug = forms.SlugField(label="Slug", help_text="URL-safe identifier, e.g. my-org")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "password1", "password2", "org_name", "slug")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user
