from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinLengthValidator, FileExtensionValidator
from django.db.models import Q
import os

class UserProfile(models.Model):
    """Extended user profile for additional information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    department = models.CharField(max_length=100, blank=True)
    notification_enabled = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.user.username}'s profile"


class Label(models.Model):
    """Labels for categorizing issues"""
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6c757d')
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class IssueManager(models.Manager):
    """Custom manager for Issue model with useful querysets"""
    
    def open_issues(self):
        return self.filter(status='open')
    
    def my_issues(self, user):
        return self.filter(reporter=user)
    
    def assigned_to(self, user):
        return self.filter(assignee=user)
    
    def high_priority(self):
        return self.filter(priority__in=['high', 'critical'])
    
    def recent(self, days=7):
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=days)
        return self.filter(created_at__gte=cutoff)


class Issue(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('on_hold', 'On Hold'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('reopened', 'Reopened'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    CATEGORY_CHOICES = [
        ('bug', 'Bug'),
        ('feature', 'Feature Request'),
        ('question', 'Question'),
        ('enhancement', 'Enhancement'),
        ('documentation', 'Documentation'),
        ('task', 'Task'),
    ]

    # Basic Information
    title = models.CharField(
        max_length=200,
        validators=[MinLengthValidator(5, 'Title must be at least 5 characters')]
    )
    description = models.TextField(
        validators=[MinLengthValidator(10, 'Description must be at least 10 characters')]
    )
    
    # Classification
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='bug', db_index=True)
    
    # AI-generated category (from NLP)
    ai_suggested_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, null=True, blank=True)
    ai_confidence = models.FloatField(null=True, blank=True, help_text="AI confidence score 0-1")
    
    # People
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reported_issues')
    assignee = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='assigned_issues'
    )
    watchers = models.ManyToManyField(User, blank=True, related_name='watched_issues')
    
    # Relationships
    labels = models.ManyToManyField(Label, blank=True, related_name='issues')
    parent_issue = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='sub_issues'
    )
    duplicate_of = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='duplicates'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Metrics
    views_count = models.PositiveIntegerField(default=0)
    upvotes = models.PositiveIntegerField(default=0)
    
    # Estimated and actual time
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    
    # Custom manager
    objects = IssueManager()
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['created_at']),
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['reporter']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"#{self.id} - {self.title}"

    def save(self, *args, **kwargs):
        # Auto-set resolved_at
        if self.status == 'resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()
        elif self.status != 'resolved':
            self.resolved_at = None
            
        # Auto-set closed_at
        if self.status == 'closed' and not self.closed_at:
            self.closed_at = timezone.now()
        elif self.status != 'closed':
            self.closed_at = None
            
        super().save(*args, **kwargs)
    
    def time_to_resolve(self):
        """Calculate time taken to resolve"""
        if self.resolved_at:
            delta = self.resolved_at - self.created_at
            return delta.total_seconds() / 3600  # hours
        return None
    
    def is_overdue(self):
        """Check if issue is overdue based on priority"""
        if self.status in ['resolved', 'closed']:
            return False
        
        priority_hours = {
            'critical': 24,
            'high': 72,
            'medium': 168,
            'low': 336
        }
        
        hours_limit = priority_hours.get(self.priority, 168)
        age = (timezone.now() - self.created_at).total_seconds() / 3600
        return age > hours_limit


class Comment(models.Model):
    """Comments on issues"""
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(validators=[MinLengthValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_internal = models.BooleanField(default=False, help_text="Internal comment, not visible to reporters")

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.username} on Issue #{self.issue.id}"


class Attachment(models.Model):
    """File attachments for issues"""
    ALLOWED_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'jpg', 'jpeg', 'png', 'gif', 'zip', 'rar']
    
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(
        upload_to='attachments/%Y/%m/%d/',
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_EXTENSIONS)]
    )
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.filename
    
    def save(self, *args, **kwargs):
        if self.file:
            self.file_size = self.file.size
            self.filename = os.path.basename(self.file.name)
        super().save(*args, **kwargs)
    
    def get_file_size_display(self):
        """Return human-readable file size"""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class ActivityLog(models.Model):
    """Activity log for tracking all changes"""
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('commented', 'Commented'),
        ('status_changed', 'Status Changed'),
        ('priority_changed', 'Priority Changed'),
        ('assigned', 'Assigned'),
        ('unassigned', 'Unassigned'),
        ('labeled', 'Labeled'),
        ('unlabeled', 'Unlabeled'),
        ('attached', 'Attached File'),
        ('closed', 'Closed'),
        ('reopened', 'Reopened'),
    ]
    
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    details = models.TextField()
    old_value = models.CharField(max_length=200, blank=True)
    new_value = models.CharField(max_length=200, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.action} on Issue #{self.issue.id}"


class Notification(models.Model):
    """User notifications"""
    NOTIFICATION_TYPES = [
        ('assigned', 'Assigned to Issue'),
        ('mentioned', 'Mentioned in Comment'),
        ('status_change', 'Issue Status Changed'),
        ('new_comment', 'New Comment'),
        ('issue_updated', 'Issue Updated'),
    ]
    
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE)
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.recipient.username}"


class IssueTemplate(models.Model):
    """Templates for creating common issue types"""
    name = models.CharField(max_length=100)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=Issue.CATEGORY_CHOICES)
    priority = models.CharField(max_length=20, choices=Issue.PRIORITY_CHOICES)
    template_content = models.TextField(help_text="Template for issue description")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name


class SavedFilter(models.Model):
    """Save custom filters for quick access"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_filters')
    name = models.CharField(max_length=100)
    filter_params = models.JSONField(help_text="Stored filter parameters")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"