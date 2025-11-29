"""
Django signals for automatic actions
"""

from django.db.models.signals import post_save, pre_save, m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Issue, Comment, UserProfile, ActivityLog
from .ml_utils import IssueClassifier
from .utils import notify_assignee, notify_watchers, log_activity


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create UserProfile when User is created
    """
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Save UserProfile when User is saved
    """
    if hasattr(instance, 'profile'):
        instance.profile.save()


@receiver(post_save, sender=Issue)
def auto_categorize_issue(sender, instance, created, **kwargs):
    """
    Automatically categorize issue using NLP when created
    Only runs on creation and if AI categorization is enabled
    """
    if created and not instance.ai_suggested_category:
        try:
            # Use NLP to suggest category
            suggested_category, confidence = IssueClassifier.classify_category(
                instance.title,
                instance.description
            )
            
            # Only update if confidence is reasonable
            if confidence > 0.4:
                # Update without triggering another save
                Issue.objects.filter(pk=instance.pk).update(
                    ai_suggested_category=suggested_category,
                    ai_confidence=confidence
                )
        except Exception as e:
            # Log error but don't fail the save
            print(f"AI categorization failed: {str(e)}")


@receiver(post_save, sender=Issue)
def log_issue_creation(sender, instance, created, **kwargs):
    """
    Log activity when issue is created
    """
    if created:
        try:
            log_activity(
                issue=instance,
                user=instance.reporter,
                action='created',
                details=f'Created issue: {instance.title}'
            )
            
            # Auto-add reporter as watcher
            instance.watchers.add(instance.reporter)
        except Exception as e:
            print(f"Failed to log issue creation: {str(e)}")


@receiver(pre_save, sender=Issue)
def track_issue_changes(sender, instance, **kwargs):
    """
    Track changes to issue fields before saving
    """
    if instance.pk:  # Only for existing issues
        try:
            old_instance = Issue.objects.get(pk=instance.pk)
            
            # Store old values for comparison in post_save
            instance._old_status = old_instance.status
            instance._old_priority = old_instance.priority
            instance._old_assignee = old_instance.assignee
        except Issue.DoesNotExist:
            pass


@receiver(post_save, sender=Issue)
def notify_on_changes(sender, instance, created, **kwargs):
    """
    Send notifications when issue is updated
    """
    if not created and instance.pk:
        try:
            # Check for status change
            if hasattr(instance, '_old_status') and instance._old_status != instance.status:
                log_activity(
                    issue=instance,
                    user=getattr(instance, '_modified_by', instance.reporter),
                    action='status_changed',
                    details=f'Status changed',
                    old_value=instance._old_status,
                    new_value=instance.status
                )
                notify_watchers(
                    instance,
                    getattr(instance, '_modified_by', instance.reporter),
                    'changed status',
                    f'from {instance._old_status} to {instance.status}'
                )
            
            # Check for priority change
            if hasattr(instance, '_old_priority') and instance._old_priority != instance.priority:
                log_activity(
                    issue=instance,
                    user=getattr(instance, '_modified_by', instance.reporter),
                    action='priority_changed',
                    details=f'Priority changed',
                    old_value=instance._old_priority,
                    new_value=instance.priority
                )
            
            # Check for assignee change
            if hasattr(instance, '_old_assignee') and instance._old_assignee != instance.assignee:
                if instance.assignee:
                    notify_assignee(instance, getattr(instance, '_modified_by', instance.reporter))
                    log_activity(
                        issue=instance,
                        user=getattr(instance, '_modified_by', instance.reporter),
                        action='assigned',
                        details=f'Assigned to {instance.assignee.username}'
                    )
                    # Auto-add assignee as watcher
                    instance.watchers.add(instance.assignee)
                else:
                    log_activity(
                        issue=instance,
                        user=getattr(instance, '_modified_by', instance.reporter),
                        action='unassigned',
                        details='Unassigned issue'
                    )
        except Exception as e:
            print(f"Failed to send notifications: {str(e)}")


@receiver(post_save, sender=Comment)
def log_comment_activity(sender, instance, created, **kwargs):
    """
    Log activity and notify when comment is added
    """
    if created:
        try:
            log_activity(
                issue=instance.issue,
                user=instance.author,
                action='commented',
                details=f'Added a comment'
            )
            
            # Notify watchers about new comment
            notify_watchers(
                issue=instance.issue,
                actor=instance.author,
                action='commented',
                details=f'Added a comment'
            )
            
            # Auto-add commenter as watcher
            instance.issue.watchers.add(instance.author)
        except Exception as e:
            print(f"Failed to log comment: {str(e)}")


@receiver(m2m_changed, sender=Issue.labels.through)
def log_label_changes(sender, instance, action, pk_set, **kwargs):
    """
    Log when labels are added or removed
    """
    if action in ['post_add', 'post_remove']:
        try:
            from .models import Label
            
            if action == 'post_add':
                labels = Label.objects.filter(pk__in=pk_set)
                for label in labels:
                    log_activity(
                        issue=instance,
                        user=getattr(instance, '_modified_by', instance.reporter),
                        action='labeled',
                        details=f'Added label: {label.name}'
                    )
            elif action == 'post_remove':
                labels = Label.objects.filter(pk__in=pk_set)
                for label in labels:
                    log_activity(
                        issue=instance,
                        user=getattr(instance, '_modified_by', instance.reporter),
                        action='unlabeled',
                        details=f'Removed label: {label.name}'
                    )
        except Exception as e:
            print(f"Failed to log label changes: {str(e)}")


@receiver(post_save, sender=Issue)
def check_overdue_issues(sender, instance, **kwargs):
    """
    Check if issue is overdue and send notification
    """
    if instance.status in ['open', 'in_progress']:
        if instance.is_overdue() and instance.assignee:
            try:
                from .utils import create_notification
                
                create_notification(
                    recipient=instance.assignee,
                    issue=instance,
                    notification_type='issue_updated',
                    message=f'Issue #{instance.id} is overdue and needs attention'
                )
            except Exception as e:
                print(f"Failed to send overdue notification: {str(e)}")