from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('', views.index, name='index'),

    # スロット編集API
    path('api/candidates/<int:slot_id>/', views.get_candidates, name='get_candidates'),
    path('api/assign/<int:slot_id>/', views.assign_staff, name='assign_staff'),
    path('api/regenerate/', views.regenerate_shift, name='regenerate_shift'),

    # 出勤管理API
    path('api/attendance/add/', views.add_daily_attendance, name='add_daily_attendance'),
    path('api/attendance/remove/', views.remove_daily_attendance, name='remove_daily_attendance'),
    path('api/attendance/update/', views.update_attendance, name='update_attendance'),
    path('api/attendance/delete/', views.delete_attendance, name='delete_attendance'),

    # スタッフ管理
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', views.staff_add, name='staff_add'),
    path('staff/<int:staff_id>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<int:staff_id>/delete/', views.staff_delete, name='staff_delete'),
    path('api/staff/bulk-level/', views.staff_bulk_level, name='staff_bulk_level'),

    # シフト取込
    path('shift-upload/', views.shift_upload, name='shift_upload'),
]
