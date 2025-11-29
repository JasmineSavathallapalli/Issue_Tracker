# ============================================
# FILE: issue_tracker_app/views.py
# ============================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.db.models import Q, Count, Avg, F
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import timedelta
import json

from .models import (
    Issue, Comment, Label, Attachment, ActivityLog,
    Notification, IssueTemplate, SavedFilter, UserProfile
)
from .forms import (
    IssueForm, IssueUpdateForm, CommentForm, AttachmentForm,
    UserRegistrationForm, UserProfileForm, LabelForm, IssueTemplateForm
)
from .ml_utils import IssueClassifier
from .utils import (
    log_activity, notify_watchers, get_issue_statistics, export_issues_csv
)


def register(request):
    """User registration"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Welcome! Your account has been created successfully.')
            return redirect('dashboard')
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def dashboard(request):
    """Enhanced dashboard with comprehensive statistics"""
    # Get statistics
    stats = get_issue_statistics()
    
    # My issues
    my_issues = Issue.objects.my_issues(request.user).order_by('-created_at')[:5]
    
    # Assigned to me
    assigned_to_me = Issue.objects.assigned_to(request.user).filter(
        status__in=['open', 'in_progress', 'on_hold']
    ).order_by('-priority', '-created_at')[:5]
    
    # Recent activity
    recent_activity = ActivityLog.objects.filter(
        issue__in=Issue.objects.filter(
            Q(reporter=request.user) | Q(assignee=request.user)
        )
    ).order_by('-timestamp')[:10]
    
    # Unread notifications
    unread_notifications = request.user.notifications.filter(is_read=False).count()
    
    # Issues by status (for chart)
    status_distribution = Issue.objects.values('status').annotate(count=Count('id'))
    
    # Priority distribution
    priority_distribution = Issue.objects.values('priority').annotate(count=Count('id'))
    
    # Recent issues (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_issues_trend = []
    for i in range(30, -1, -5):
        date = timezone.now() - timedelta(days=i)
        count = Issue.objects.filter(created_at__date=date.date()).count()
        recent_issues_trend.append({
            'date': date.strftime('%m/%d'),
            'count': count
        })
    
    # Overdue issues
    overdue_count = sum(1 for issue in Issue.objects.filter(
        status__in=['open', 'in_progress']
    ) if issue.is_overdue())
    
    context = {
        'stats': stats,
        'my_issues': my_issues,
        'assigned_to_me': assigned_to_me,
        'recent_activity': recent_activity,
        'unread_notifications': unread_notifications,
        'status_distribution': list(status_distribution),
        'priority_distribution': list(priority_distribution),
        'recent_issues_trend': recent_issues_trend,
        'overdue_count': overdue_count,
    }
    return render(request, 'issue_tracker_app/dashboard.html', context)


@login_required
def issue_list(request):
    """Enhanced issue list with advanced filtering and search"""
    issues = Issue.objects.select_related('reporter', 'assignee').prefetch_related('labels')
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    category_filter = request.GET.get('category', '')
    assignee_filter = request.GET.get('assignee', '')
    reporter_filter = request.GET.get('reporter', '')
    label_filter = request.GET.get('label', '')
    search_query = request.GET.get('search', '')
    sort_by = request.GET.get('sort', '-created_at')
    
    # Apply filters
    if status_filter:
        issues = issues.filter(status=status_filter)
    if priority_filter:
        issues = issues.filter(priority=priority_filter)
    if category_filter:
        issues = issues.filter(category=category_filter)
    if assignee_filter:
        if assignee_filter == 'unassigned':
            issues = issues.filter(assignee__isnull=True)
        elif assignee_filter == 'me':
            issues = issues.filter(assignee=request.user)
        else:
            issues = issues.filter(assignee_id=assignee_filter)
    if reporter_filter:
        if reporter_filter == 'me':
            issues = issues.filter(reporter=request.user)
        else:
            issues = issues.filter(reporter_id=reporter_filter)
    if label_filter:
        issues = issues.filter(labels__id=label_filter)
    if search_query:
        issues = issues.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query) |
            Q(id__icontains=search_query)
        )
    
    # Sorting
    if sort_by:
        issues = issues.order_by(sort_by)
    
    # Pagination
    paginator = Paginator(issues, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get all users for assignee filter
    from django.contrib.auth.models import User
    users = User.objects.filter(is_active=True).order_by('username')
    
    # Get all labels
    labels = Label.objects.all()
    
    # Get saved filters for current user
    saved_filters = SavedFilter.objects.filter(user=request.user)
    
    context = {
        'page_obj': page_obj,
        'status_choices': Issue.STATUS_CHOICES,
        'priority_choices': Issue.PRIORITY_CHOICES,
        'category_choices': Issue.CATEGORY_CHOICES,
        'users': users,
        'labels': labels,
        'saved_filters': saved_filters,
        'current_filters': {
            'status': status_filter,
            'priority': priority_filter,
            'category': category_filter,
            'assignee': assignee_filter,
            'reporter': reporter_filter,
            'label': label_filter,
            'search': search_query,
            'sort': sort_by,
        }
    }
    return render(request, 'issue_tracker_app/issue_list.html', context)


@login_required
def issue_detail(request, pk):
    """Detailed issue view with comments and activity"""
    issue = get_object_or_404(
        Issue.objects.select_related('reporter', 'assignee')
        .prefetch_related('labels', 'comments__author', 'attachments', 'activities__user'),
        pk=pk
    )
    
    # Increment view count
    issue.views_count += 1
    issue.save(update_fields=['views_count'])
    
    # Get related data
    comments = issue.comments.all()
    attachments = issue.attachments.all()
    activities = issue.activities.all()[:20]
    sub_issues = issue.sub_issues.all()
    
    # Check if user is watching
    is_watching = request.user in issue.watchers.all()
    
    # Handle comment submission
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        attachment_form = AttachmentForm(request.POST, request.FILES)
        
        if 'submit_comment' in request.POST and comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.issue = issue
            comment.author = request.user
            comment.save()
            
            log_activity(
                issue=issue,
                user=request.user,
                action='commented',
                details='Added a comment'
            )
            
            notify_watchers(issue, request.user, 'commented', 'Added a comment')
            
            messages.success(request, 'Comment added successfully!')
            return redirect('issue_detail', pk=pk)
        
        elif 'submit_attachment' in request.POST and attachment_form.is_valid():
            attachment = attachment_form.save(commit=False)
            attachment.issue = issue
            attachment.uploaded_by = request.user
            attachment.save()
            
            log_activity(
                issue=issue,
                user=request.user,
                action='attached',
                details=f'Attached file: {attachment.filename}'
            )
            
            messages.success(request, 'File attached successfully!')
            return redirect('issue_detail', pk=pk)
    else:
        comment_form = CommentForm()
        attachment_form = AttachmentForm()
    
    context = {
        'issue': issue,
        'comments': comments,
        'attachments': attachments,
        'activities': activities,
        'sub_issues': sub_issues,
        'comment_form': comment_form,
        'attachment_form': attachment_form,
        'is_watching': is_watching,
    }
    return render(request, 'issue_tracker_app/issue_detail.html', context)


@login_required
def issue_create(request):
    """Create new issue with AI-powered categorization"""
    if request.method == 'POST':
        form = IssueForm(request.POST)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.reporter = request.user
            
            # AI categorization (if user wants suggestion)
            if request.POST.get('use_ai_categorization'):
                suggested_category, confidence = IssueClassifier.classify_category(
                    issue.title,
                    issue.description
                )
                issue.category = suggested_category
                issue.ai_suggested_category = suggested_category
                issue.ai_confidence = confidence
                
                # Also suggest priority
                suggested_priority = IssueClassifier.suggest_priority(
                    issue.title,
                    issue.description
                )
                issue.priority = suggested_priority
            
            issue.save()
            form.save_m2m()  # Save many-to-many relationships (labels)
            
            # Automatically add reporter as watcher
            issue.watchers.add(request.user)
            
            log_activity(
                issue=issue,
                user=request.user,
                action='created',
                details=f'Created issue: {issue.title}'
            )
            
            messages.success(
                request, 
                f'Issue #{issue.id} created successfully! '
                f'{"AI suggested: " + issue.get_category_display() if issue.ai_suggested_category else ""}'
            )
            return redirect('issue_detail', pk=issue.pk)
    else:
        form = IssueForm()
        
        # Pre-fill from template if specified
        template_id = request.GET.get('template')
        if template_id:
            try:
                template = IssueTemplate.objects.get(id=template_id, is_active=True)
                form.initial = {
                    'category': template.category,
                    'priority': template.priority,
                    'description': template.template_content
                }
            except IssueTemplate.DoesNotExist:
                pass
    
    # Get available templates
    templates = IssueTemplate.objects.filter(is_active=True)
    
    context = {
        'form': form,
        'action': 'Create',
        'templates': templates
    }
    return render(request, 'issue_tracker_app/issue_form.html', context)


@login_required
def issue_update(request, pk):
    """Update existing issue"""
    issue = get_object_or_404(Issue, pk=pk)
    old_status = issue.status
    old_priority = issue.priority
    old_assignee = issue.assignee
    
    if request.method == 'POST':
        form = IssueUpdateForm(request.POST, instance=issue)
        if form.is_valid():
            updated_issue = form.save()
            
            # Log specific changes
            if old_status != updated_issue.status:
                log_activity(
                    issue=issue,
                    user=request.user,
                    action='status_changed',
                    details=f'Status changed',
                    old_value=old_status,
                    new_value=updated_issue.status
                )
                notify_watchers(
                    issue,
                    request.user,
                    'changed status',
                    f'from {old_status} to {updated_issue.status}'
                )
            
            if old_priority != updated_issue.priority:
                log_activity(
                    issue=issue,
                    user=request.user,
                    action='priority_changed',
                    details=f'Priority changed',
                    old_value=old_priority,
                    new_value=updated_issue.priority
                )
            
            if old_assignee != updated_issue.assignee:
                if updated_issue.assignee:
                    log_activity(
                        issue=issue,
                        user=request.user,
                        action='assigned',
                        details=f'Assigned to {updated_issue.assignee.username}'
                    )
                else:
                    log_activity(
                        issue=issue,
                        user=request.user,
                        action='unassigned',
                        details='Unassigned issue'
                    )
            
            messages.success(request, 'Issue updated successfully!')
            return redirect('issue_detail', pk=pk)
    else:
        form = IssueUpdateForm(instance=issue)
    
    context = {
        'form': form,
        'action': 'Update',
        'issue': issue
    }
    return render(request, 'issue_tracker_app/issue_form.html', context)


@login_required
def issue_delete(request, pk):
    """Delete issue"""
    issue = get_object_or_404(Issue, pk=pk)
    
    # Only reporter or admin can delete
    if request.user != issue.reporter and not request.user.is_staff:
        messages.error(request, 'You do not have permission to delete this issue.')
        return redirect('issue_detail', pk=pk)
    
    if request.method == 'POST':
        issue.delete()
        messages.success(request, f'Issue #{pk} deleted successfully!')
        return redirect('issue_list')
    
    return render(request, 'issue_tracker_app/issue_confirm_delete.html', {'issue': issue})


@login_required
@require_POST
def toggle_watch(request, pk):
    """Toggle watching an issue"""
    issue = get_object_or_404(Issue, pk=pk)
    
    if request.user in issue.watchers.all():
        issue.watchers.remove(request.user)
        is_watching = False
        message = 'You are no longer watching this issue.'
    else:
        issue.watchers.add(request.user)
        is_watching = True
        message = 'You are now watching this issue.'
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'is_watching': is_watching, 'message': message})
    
    messages.success(request, message)
    return redirect('issue_detail', pk=pk)


@login_required
def analytics(request):
    """Analytics and reporting page"""
    stats = get_issue_statistics()
    
    # Time-based statistics
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    
    # Issues created per day (last 30 days)
    issues_per_day = []
    for i in range(29, -1, -1):
        date = (now - timedelta(days=i)).date()
        count = Issue.objects.filter(created_at__date=date).count()
        issues_per_day.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': count
        })
    
    # Resolution time analysis
    resolved_issues = Issue.objects.filter(
        resolved_at__isnull=False,
        created_at__gte=thirty_days_ago
    )
    
    resolution_times = []
    for issue in resolved_issues:
        hours = issue.time_to_resolve()
        if hours:
            resolution_times.append({
                'issue_id': issue.id,
                'hours': round(hours, 1),
                'priority': issue.priority
            })
    
    # Top contributors
    top_reporters = Issue.objects.values('reporter__username').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    top_resolvers = Issue.objects.filter(
        assignee__isnull=False,
        status__in=['resolved', 'closed']
    ).values('assignee__username').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    context = {
        'stats': stats,
        'issues_per_day': issues_per_day,
        'resolution_times': resolution_times,
        'top_reporters': list(top_reporters),
        'top_resolvers': list(top_resolvers),
    }
    return render(request, 'issue_tracker_app/analytics.html', context)


@login_required
def export_issues(request):
    """Export issues to CSV"""
    issues = Issue.objects.all()
    
    # Apply same filters as issue_list
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    category_filter = request.GET.get('category', '')
    
    if status_filter:
        issues = issues.filter(status=status_filter)
    if priority_filter:
        issues = issues.filter(priority=priority_filter)
    if category_filter:
        issues = issues.filter(category=category_filter)
    
    csv_data = export_issues_csv(issues)
    
    response = HttpResponse(csv_data, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="issues_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    return response


@login_required
def label_list(request):
    """Manage labels"""
    labels = Label.objects.annotate(issue_count=Count('issues')).order_by('name')
    
    if request.method == 'POST':
        form = LabelForm(request.POST)
        if form.is_valid():
            label = form.save(commit=False)
            label.created_by = request.user
            label.save()
            messages.success(request, f'Label "{label.name}" created successfully!')
            return redirect('label_list')
    else:
        form = LabelForm()
    
    context = {
        'labels': labels,
        'form': form
    }
    return render(request, 'issue_tracker_app/label_list.html', context)


@login_required
def notifications(request):
    """View all notifications"""
    all_notifications = request.user.notifications.select_related('issue').order_by('-created_at')
    
    # Mark as read if requested
    if request.method == 'POST':
        notification_id = request.POST.get('notification_id')
        if notification_id:
            try:
                notification = all_notifications.get(id=notification_id)
                notification.is_read = True
                notification.save()
            except Notification.DoesNotExist:
                pass
    
    # Pagination
    paginator = Paginator(all_notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'unread_count': all_notifications.filter(is_read=False).count()
    }
    return render(request, 'issue_tracker_app/notifications.html', context)


@login_required
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    if request.method == 'POST':
        request.user.notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, 'All notifications marked as read.')
    return redirect('notifications')


@login_required
def settings_view(request):
    """User settings page"""
    profile = request.user.profile
    
    if request.method == 'POST':
        profile_form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, 'Settings updated successfully!')
            return redirect('settings')
    else:
        profile_form = UserProfileForm(instance=profile)
    
    context = {
        'profile_form': profile_form
    }
    return render(request, 'issue_tracker_app/settings.html', context)