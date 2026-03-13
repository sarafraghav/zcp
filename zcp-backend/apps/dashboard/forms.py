from django import forms


class CreateOrgForm(forms.Form):
    org_name = forms.CharField(max_length=255, label="Organization name")
    slug = forms.SlugField(label="Slug", help_text="URL-safe identifier, e.g. my-org")
