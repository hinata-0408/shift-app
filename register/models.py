from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Staff(models.Model):
    LEVEL_CHOICES = [
        (0, 'Lv0 - 戦力外'),
        (1, 'Lv1 - 最優先'),
        (2, 'Lv2 - 通常'),
        (3, 'Lv3 - なるべく避ける'),
        (4, 'Lv4 - 原則避ける'),
    ]

    DEPARTMENT_CHOICES = [
        ('店長', '店長'),
        ('季節', '季節'),
        ('家電', '家電'),
        ('情報', '情報'),
        ('通信', '通信'),
    ]

    name = models.CharField('名前', max_length=50, unique=True)
    level = models.IntegerField('レベル', choices=LEVEL_CHOICES, default=2)
    department = models.CharField('部門', max_length=20, choices=DEPARTMENT_CHOICES, default='季節')
    display_order = models.IntegerField('表示順', default=9999)
    is_active = models.BooleanField('有効', default=True)
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    class Meta:
        verbose_name = 'スタッフ'
        verbose_name_plural = 'スタッフ'
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"{self.name} (Lv{self.level})"


class DailyAttendance(models.Model):
    SHIFT_TYPE_CHOICES = [
        ('早', '早番'),
        ('遅', '遅番'),
        ('流早', '流し早番'),
        ('流遅', '流し遅番'),
        ('通し', '通し'),
        ('その他', 'その他'),
    ]

    date = models.DateField('日付')
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, verbose_name='スタッフ')
    start_hour = models.IntegerField('出勤時間（時）', default=10)
    start_min = models.IntegerField('出勤時間（分）', default=0)
    end_hour = models.IntegerField('退勤時間（時）', default=19)
    end_min = models.IntegerField('退勤時間（分）', default=0)
    shift_type = models.CharField('シフト種別', max_length=10, choices=SHIFT_TYPE_CHOICES, default='早')

    class Meta:
        verbose_name = '出勤情報'
        verbose_name_plural = '出勤情報'
        unique_together = ['date', 'staff']
        ordering = ['date', 'start_hour', 'start_min']

    def __str__(self):
        return f"{self.date} {self.staff.name} ({self.start_hour}:{self.start_min:02d}-{self.end_hour}:{self.end_min:02d})"

    @property
    def start_time_str(self):
        return f"{self.start_hour}:{self.start_min:02d}"

    @property
    def end_time_str(self):
        return f"{self.end_hour}:{self.end_min:02d}"


class RegisterSlot(models.Model):
    date = models.DateField('日付')
    start_hour = models.IntegerField('開始時間')
    end_hour = models.IntegerField('終了時間')
    assigned_staff = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='担当者'
    )
    is_auto_generated = models.BooleanField('自動生成', default=True)
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)
    last_edited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='最終編集者'
    )

    class Meta:
        verbose_name = 'レジシフト枠'
        verbose_name_plural = 'レジシフト枠'
        unique_together = ['date', 'start_hour']
        ordering = ['date', 'start_hour']

    def __str__(self):
        staff_name = self.assigned_staff.name if self.assigned_staff else '未割当'
        return f"{self.date} {self.start_hour}時〜 → {staff_name}"

    @property
    def time_label(self):
        return f"{self.start_hour}:00-{self.end_hour}:00"


class EditHistory(models.Model):
    slot = models.ForeignKey(RegisterSlot, on_delete=models.CASCADE, verbose_name='対象枠')
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='編集者')
    edited_at = models.DateTimeField('編集日時', default=timezone.now)
    previous_staff = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='previous_assignments',
        verbose_name='変更前'
    )
    new_staff = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='new_assignments',
        verbose_name='変更後'
    )

    class Meta:
        verbose_name = '編集履歴'
        verbose_name_plural = '編集履歴'
        ordering = ['-edited_at']

    def __str__(self):
        prev = self.previous_staff.name if self.previous_staff else '未割当'
        new = self.new_staff.name if self.new_staff else '未割当'
        return f"{self.edited_at:%H:%M} {prev} → {new}"
