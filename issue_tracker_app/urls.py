# ============================================
# FILE: issue_tracker_app/urls.py
# ============================================

from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Issues
    path('issues/', views.issue_list, name='issue_list'),
    path('issues/create/', views.issue_create, name='issue_create'),
    path('issues/<int:pk>/', views.issue_detail, name='issue_detail'),
    path('issues/<int:pk>/update/', views.issue_update, name='issue_update'),
    path('issues/<int:pk>/delete/', views.issue_delete, name='issue_delete'),
    path('issues/<int:pk>/toggle-watch/', views.toggle_watch, name='toggle_watch'),
    
    # Export
    path('issues/export/', views.export_issues, name='export_issues'),
    
    # Labels
    path('labels/', views.label_list, name='label_list'),
    
    # Analytics
    path('analytics/', views.analytics, name='analytics'),
    
    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # Settings
    path('settings/', views.settings_view, name='settings'),
    
    # Authentication
    path('register/', views.register, name='register'),
]
