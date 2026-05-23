from django.contrib import admin
from .models import Staff, DailyAttendance, RegisterSlot, EditHistory


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['name', 'level', 'department', 'is_active', 'created_at']
    list_filter = ['level', 'department', 'is_active']
    search_fields = ['name']
    list_editable = ['level', 'is_active']
    ordering = ['level', 'name']


@admin.register(DailyAttendance)
class DailyAttendanceAdmin(admin.ModelAdmin):
    list_display = ['date', 'staff', 'shift_type', 'start_hour', 'end_hour']
    list_filter = ['date', 'shift_type']
    search_fields = ['staff__name']
    date_hierarchy = 'date'


@admin.register(RegisterSlot)
class RegisterSlotAdmin(admin.ModelAdmin):
    list_display = ['date', 'start_hour', 'assigned_staff', 'is_auto_generated', 'last_edited_by', 'updated_at']
    list_filter = ['date', 'is_auto_generated']
    search_fields = ['assigned_staff__name']
    date_hierarchy = 'date'


@admin.register(EditHistory)
class EditHistoryAdmin(admin.ModelAdmin):
    list_display = ['edited_at', 'slot', 'edited_by', 'previous_staff', 'new_staff']
    list_filter = ['edited_at', 'edited_by']
    date_hierarchy = 'edited_at'
