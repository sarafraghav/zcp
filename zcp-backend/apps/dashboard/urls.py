from django.urls import path
from . import views

urlpatterns = [
    path("", views.SignupView.as_view(), name="signup"),
    path("status/<str:workflow_id>/", views.WorkflowStatusView.as_view(), name="signup-status"),
]

onboarding_urlpatterns = [
    path("", views.OnboardingWelcomeView.as_view(), name="welcome"),
    path("schema/", views.OnboardingSchemaView.as_view(), name="schema"),
    path("apikey/", views.OnboardingApiKeyView.as_view(), name="apikey"),
    path("deploy/", views.OnboardingDeployView.as_view(), name="deploy"),
    path("deploy/status/<str:workflow_id>/", views.OnboardingDeployStatusView.as_view(), name="deploy-status"),
]

dashboard_urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("databases/", views.DatabaseListView.as_view(), name="database-list"),
    path("databases/<uuid:db_id>/query/", views.QueryDatabaseView.as_view(), name="database-query"),
    path("redis/", views.RedisListView.as_view(), name="redis-list"),
    path("redis/<uuid:redis_id>/command/", views.RedisCommandView.as_view(), name="redis-command"),
    path("apps/", views.AppsListView.as_view(), name="apps-list"),
    path("projects/create/", views.CreateProjectView.as_view(), name="project-create"),
    path("projects/<uuid:project_id>/redeploy/", views.RedeployProjectView.as_view(), name="project-redeploy"),
    path("projects/status/<str:workflow_id>/", views.ProjectDeployStatusView.as_view(), name="project-status"),
    path("orgs/create/", views.CreateOrgView.as_view(), name="org-create"),
    path("orgs/status/<str:workflow_id>/", views.OrgWorkflowStatusView.as_view(), name="org-status"),
    path("orgs/<uuid:org_id>/switch/", views.SwitchOrgView.as_view(), name="org-switch"),
    path("orgs/<uuid:org_id>/delete/", views.DeleteOrgView.as_view(), name="org-delete"),
    path("orgs/<uuid:org_id>/delete/status/", views.DeleteOrgStatusView.as_view(), name="org-delete-status"),
    path("apikeys/", views.APIKeyListView.as_view(), name="apikey-list"),
    path("apikeys/<uuid:key_id>/regenerate/", views.RegenerateAPIKeyView.as_view(), name="apikey-regenerate"),
]
