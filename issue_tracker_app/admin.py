from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Issue, Comment, Label, Attachment, ActivityLog,
    UserProfile, Notification, IssueTemplate, SavedFilter
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'phone', 'notification_enabled']
    list_filter = ['notification_enabled', 'email_notifications', 'department']
    search_fields = ['user__username', 'user__email', 'phone']


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'title', 'status_badge', 'priority_badge', 
        'category', 'reporter', 'assignee', 'created_at'
    ]
    list_filter = ['status', 'priority', 'category', 'created_at']
    search_fields = ['title', 'description', 'id']
    date_hierarchy = 'created_at'
    raw_id_fields = ['reporter', 'assignee', 'parent_issue', 'duplicate_of']
    filter_horizontal = ['labels', 'watchers']
    readonly_fields = [
        'created_at', 'updated_at', 'resolved_at', 
        'closed_at', 'views_count', 'ai_suggested_category', 'ai_confidence'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'category', 'ai_suggested_category', 'ai_confidence')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority')
        }),
        ('Assignment', {
            'fields': ('reporter', 'assignee', 'watchers')
        }),
        ('Classification', {
            'fields': ('labels',)
        }),
        ('Relationships', {
            'fields': ('parent_issue', 'duplicate_of'),
            'classes': ('collapse',)
        }),
        ('Time Tracking', {
            'fields': ('estimated_hours', 'actual_hours', 'created_at', 'updated_at', 'resolved_at', 'closed_at'),
            'classes': ('collapse',)
        }),
        ('Metrics', {
            'fields': ('views_count', 'upvotes'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'open': '#28a745',
            'in_progress': '#17a2b8',
            'on_hold': '#ffc107',
            'resolved': '#6f42c1',
            'closed': '#6c757d',
            'reopened': '#fd7e14'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def priority_badge(self, obj):
        colors = {
            'low': '#6c757d',
            'medium': '#ffc107',
            'high': '#fd7e14',
            'critical': '#dc3545'
        }
        color = colors.get(obj.priority, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_priority_display()
        )
    priority_badge.short_description = 'Priority'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'issue', 'author', 'is_internal', 'created_at']
    list_filter = ['is_internal', 'created_at']
    search_fields = ['content', 'issue__title']
    raw_id_fields = ['issue', 'author']


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ['name', 'color_preview', 'issue_count', 'created_at']
    search_fields = ['name', 'description']
    
    def color_preview(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 5px 15px; '
            'border-radius: 3px; color: white;">{}</span>',
            obj.color, obj.color
        )
    color_preview.short_description = 'Color'
    
    def issue_count(self, obj):
        return obj.issues.count()
    issue_count.short_description = 'Issues'


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'issue', 'file_size_display', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['filename', 'description']
    raw_id_fields = ['issue', 'uploaded_by']
    
    def file_size_display(self, obj):
        return obj.get_file_size_display()
    file_size_display.short_description = 'Size'


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['issue', 'user', 'action', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['details']
    raw_id_fields = ['issue', 'user']
    date_hierarchy = 'timestamp'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notification_type', 'issue', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    raw_id_fields = ['recipient', 'issue']


@admin.register(IssueTemplate)
class IssueTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'priority', 'is_active', 'created_by', 'created_at']
    list_filter = ['category', 'priority', 'is_active']
    search_fields = ['name', 'description']
    raw_id_fields = ['created_by']


@admin.register(SavedFilter)
class SavedFilterAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'is_default', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['name']
    raw_id_fields = ['user']