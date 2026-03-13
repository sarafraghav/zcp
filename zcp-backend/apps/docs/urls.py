from django.urls import path
from apps.docs.views import SpecView, SchemaJsonView

app_name = "docs"

urlpatterns = [
    path("spec/", SpecView.as_view(), name="spec"),
    path("schema.json", SchemaJsonView.as_view(), name="schema-json"),
]
