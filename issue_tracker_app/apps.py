from django.apps import AppConfig

class IssueTrackerAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'issue_tracker_app'
    verbose_name = 'Issue Tracker'

    def ready(self):
        # Import signals
        import issue_tracker_app.signals