from django.urls import path
from .views import DeployView

urlpatterns = [
    path("v1/deploy/", DeployView.as_view(), name="api-deploy"),
]
