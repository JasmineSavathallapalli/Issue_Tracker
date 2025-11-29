"""
Utility functions for the issue tracker
"""

from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db.models import Count, Avg, Q, F, DurationField, ExpressionWrapper
from django.utils import timezone
from datetime import timedelta
import csv
from io import StringIO


def log_activity(issue, user, action, details, old_value='', new_value=''):
    """
    Create an activity log entry
    
    Args:
        issue: Issue instance
        user: User who performed the action
        action: Action type (created, updated, etc.)
        details: Description of what happened
        old_value: Previous value (optional)
        new_value: New value (optional)
    
    Returns:
        ActivityLog instance
    """
    from .models import ActivityLog
    
    return ActivityLog.objects.create(
        issue=issue,
        user=user,
        action=action,
        details=details,
        old_value=old_value,
        new_value=new_value
    )


def create_notification(recipient, issue, notification_type, message):
    """
    Create a notification for a user
    
    Args:
        recipient: User to notify
        issue: Related issue
        notification_type: Type of notification
        message: Notification message
    
    Returns:
        Notification instance
    """
    from .models import Notification
    
    # Don't create duplicate notifications
    existing = Notification.objects.filter(
        recipient=recipient,
        issue=issue,
        notification_type=notification_type,
        is_read=False
    ).first()
    
    if existing:
        return existing
    
    return Notification.objects.create(
        recipient=recipient,
        issue=issue,
        notification_type=notification_type,
        message=message
    )


def send_email_notification(user, subject, template_name, context):
    """
    Send email notification to user
    
    Args:
        user: User to send email to
        subject: Email subject
        template_name: Template to use
        context: Context data for template
    """
    # Check if user has email notifications enabled
    if hasattr(user, 'profile') and not user.profile.email_notifications:
        return
    
    if not user.email:
        return
    
    try:
        html_message = render_to_string(template_name, context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@issuetracker.com'),
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )
    except Exception as e:
        # Log error but don't raise exception
        print(f"Failed to send email to {user.email}: {str(e)}")


def notify_assignee(issue, assigned_by):
    """
    Notify user when assigned to an issue
    
    Args:
        issue: Issue that was assigned
        assigned_by: User who assigned the issue
    """
    if issue.assignee and issue.assignee != assigned_by:
        message = f"{assigned_by.username} assigned you to issue #{issue.id}: {issue.title}"
        
        # Create in-app notification
        create_notification(
            recipient=issue.assignee,
            issue=issue,
            notification_type='assigned',
            message=message
        )
        
        # Send email notification if configured
        if hasattr(settings, 'EMAIL_HOST'):
            context = {
                'issue': issue,
                'assigned_by': assigned_by,
                'assignee': issue.assignee
            }
            send_email_notification(
                user=issue.assignee,
                subject=f'[IssueTracker] Assigned to Issue #{issue.id}',
                template_name='emails/issue_assigned.html',
                context=context
            )


def notify_watchers(issue, actor, action, details):
    """
    Notify all watchers of an issue about changes
    
    Args:
        issue: Issue that was modified
        actor: User who made the change
        action: What action was performed
        details: Details of the change
    """
    for watcher in issue.watchers.all():
        if watcher != actor:  # Don't notify the person who made the change
            message = f"{actor.username} {action} on issue #{issue.id}: {details}"
            
            create_notification(
                recipient=watcher,
                issue=issue,
                notification_type='issue_updated',
                message=message
            )


def get_issue_statistics():
    """
    Get various statistics about issues
    
    Returns:
        Dictionary with statistics
    """
    from .models import Issue
    
    total = Issue.objects.count()
    open_count = Issue.objects.filter(status='open').count()
    in_progress = Issue.objects.filter(status='in_progress').count()
    resolved = Issue.objects.filter(status='resolved').count()
    closed = Issue.objects.filter(status='closed').count()
    
    # Issues by category
    by_category = Issue.objects.values('category').annotate(count=Count('id'))
    
    # Issues by priority
    by_priority = Issue.objects.values('priority').annotate(count=Count('id'))
    
    # Recent issues (last 7 days)
    week_ago = timezone.now() - timedelta(days=7)
    recent = Issue.objects.filter(created_at__gte=week_ago).count()
    
    # Average resolution time
    resolved_issues = Issue.objects.filter(resolved_at__isnull=False)
    avg_resolution_time = None
    
    if resolved_issues.exists():
        avg_resolution_time = resolved_issues.aggregate(
            avg_time=Avg(
                ExpressionWrapper(
                    F('resolved_at') - F('created_at'),
                    output_field=DurationField()
                )
            )
        )['avg_time']
        
        if avg_resolution_time:
            # Convert to hours
            avg_resolution_time = avg_resolution_time.total_seconds() / 3600
    
    # Overdue count
    overdue_count = sum(1 for issue in Issue.objects.filter(
        status__in=['open', 'in_progress']
    ) if issue.is_overdue())
    
    return {
        'total': total,
        'open': open_count,
        'in_progress': in_progress,
        'resolved': resolved,
        'closed': closed,
        'by_category': list(by_category),
        'by_priority': list(by_priority),
        'recent': recent,
        'avg_resolution_hours': round(avg_resolution_time, 1) if avg_resolution_time else None,
        'overdue_count': overdue_count
    }


def export_issues_csv(queryset):
    """
    Export issues to CSV format
    
    Args:
        queryset: QuerySet of issues to export
    
    Returns:
        CSV string
    """
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'ID', 'Title', 'Status', 'Priority', 'Category', 
        'Reporter', 'Assignee', 'Created', 'Updated', 'Resolved',
        'Estimated Hours', 'Actual Hours', 'Labels'
    ])
    
    # Data rows
    for issue in queryset:
        labels = ', '.join([label.name for label in issue.labels.all()])
        
        writer.writerow([
            issue.id,
            issue.title,
            issue.get_status_display(),
            issue.get_priority_display(),
            issue.get_category_display(),
            issue.reporter.username,
            issue.assignee.username if issue.assignee else 'Unassigned',
            issue.created_at.strftime('%Y-%m-%d %H:%M'),
            issue.updated_at.strftime('%Y-%m-%d %H:%M'),
            issue.resolved_at.strftime('%Y-%m-%d %H:%M') if issue.resolved_at else 'Not resolved',
            issue.estimated_hours if issue.estimated_hours else '',
            issue.actual_hours if issue.actual_hours else '',
            labels
        ])
    
    return output.getvalue()


def get_user_stats(user):
    """
    Get statistics for a specific user
    
    Args:
        user: User instance
    
    Returns:
        Dictionary with user statistics
    """
    from .models import Issue
    
    reported = Issue.objects.filter(reporter=user).count()
    assigned = Issue.objects.filter(assignee=user).count()
    resolved = Issue.objects.filter(assignee=user, status='resolved').count()
    
    # Resolution rate
    resolution_rate = (resolved / assigned * 100) if assigned > 0 else 0
    
    return {
        'reported_issues': reported,
        'assigned_issues': assigned,
        'resolved_issues': resolved,
        'resolution_rate': round(resolution_rate, 1)
    }


def bulk_update_issues(issue_ids, updates):
    """
    Bulk update multiple issues
    
    Args:
        issue_ids: List of issue IDs
        updates: Dictionary of fields to update
    
    Returns:
        Number of issues updated
    """
    from .models import Issue
    
    issues = Issue.objects.filter(id__in=issue_ids)
    count = issues.update(**updates)
    
    return count


def duplicate_issue_check(title, description, threshold=0.7):
    """
    Check for potential duplicate issues
    
    Args:
        title: Issue title
        description: Issue description
        threshold: Similarity threshold (0-1)
    
    Returns:
        List of potentially duplicate issues
    """
    from .models import Issue
    from .ml_utils import IssueClassifier
    
    # Get keywords from new issue
    keywords = IssueClassifier.extract_keywords(f"{title} {description}")
    
    # Find issues with similar keywords
    potential_duplicates = []
    
    for issue in Issue.objects.filter(status__in=['open', 'in_progress'])[:100]:
        issue_keywords = IssueClassifier.extract_keywords(
            f"{issue.title} {issue.description}"
        )
        
        # Calculate similarity (simple keyword overlap)
        overlap = len(set(keywords) & set(issue_keywords))
        similarity = overlap / len(set(keywords | issue_keywords)) if keywords else 0
        
        if similarity >= threshold:
            potential_duplicates.append({
                'issue': issue,
                'similarity': round(similarity, 2)
            })
    
    # Sort by similarity
    potential_duplicates.sort(key=lambda x: x['similarity'], reverse=True)
    
    return potential_duplicates[:5]