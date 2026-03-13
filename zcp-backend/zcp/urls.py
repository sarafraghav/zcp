from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from apps.dashboard.urls import dashboard_urlpatterns

admin.site.site_header = "Zamp Control Plane"
admin.site.site_title = "ZCP Admin"
admin.site.index_title = "Internal Operations"

urlpatterns = [
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("admin/", admin.site.urls),
    path("signup/", include("apps.dashboard.urls")),
    path("dashboard/", include((dashboard_urlpatterns, "dashboard"))),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/", include("apps.api.urls")),
    path("docs/", include("apps.docs.urls")),
]
