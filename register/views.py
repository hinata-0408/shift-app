from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import date, timedelta
import json

from .models import Staff, DailyAttendance, RegisterSlot, EditHistory
from .register_logic import (
    StaffData, Slot, generate_register_shift,
    get_candidates_with_scores, total_score
)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('index')
        messages.error(request, 'ユーザー名またはパスワードが正しくありません')
    else:
        form = AuthenticationForm()

    return render(request, 'register/login.html', {'form': form})


@login_required
def index(request):
    date_str = request.GET.get('date')
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    slots = RegisterSlot.objects.filter(date=target_date).select_related('assigned_staff', 'last_edited_by')

    if not slots.exists() and DailyAttendance.objects.filter(date=target_date).exists():
        slots = generate_slots_for_date(target_date, request.user)

    attendances = DailyAttendance.objects.filter(
        date=target_date
    ).select_related('staff').order_by('staff__id')

    manager_attendances = [att for att in attendances if att.staff.department == '店長']

    dept_order = ['季節', '家電', '情報', '通信']
    attendance_by_dept = {}
    for dept in dept_order:
        dept_atts = [att for att in attendances if att.staff.department == dept]
        if dept_atts:
            attendance_by_dept[dept] = dept_atts

    histories = EditHistory.objects.filter(
        slot__date=target_date
    ).select_related('edited_by', 'previous_staff', 'new_staff', 'slot')[:20]

    working_staff_ids = set(attendances.values_list('staff_id', flat=True))

    all_staffs = list(Staff.objects.filter(is_active=True).exclude(id__in=working_staff_ids).order_by('id'))
    all_depts = ['店長', '季節', '家電', '情報', '通信']
    staffs_by_dept = {dept: [s for s in all_staffs if s.department == dept] for dept in all_depts}

    staffs_by_dept_json = json.dumps(
        {dept: [{'id': s.id, 'name': s.name} for s in staffs] for dept, staffs in staffs_by_dept.items()},
        ensure_ascii=False
    )

    context = {
        'target_date': target_date,
        'prev_date': prev_date,
        'next_date': next_date,
        'slots': slots,
        'histories': histories,
        'today': date.today(),
        'attendances': attendances,
        'attendance_by_dept': attendance_by_dept,
        'manager_attendances': manager_attendances,
        'staffs_by_dept': staffs_by_dept,
        'staffs_by_dept_json': staffs_by_dept_json,
        'all_depts': dept_order,
        'working_staff_ids': working_staff_ids,
    }

    return render(request, 'register/index.html', context)


@login_required
def get_candidates(request, slot_id):
    slot = get_object_or_404(RegisterSlot, id=slot_id)

    attendances = DailyAttendance.objects.filter(date=slot.date).select_related('staff')

    staff_counts = {}
    for s in RegisterSlot.objects.filter(date=slot.date).exclude(id=slot_id):
        if s.assigned_staff:
            staff_counts[s.assigned_staff.id] = staff_counts.get(s.assigned_staff.id, 0) + 1

    staff_list = []
    for att in attendances:
        if att.staff.level == 0:
            continue
        if not (att.start_hour <= slot.start_hour < att.end_hour):
            continue

        work_minutes = (att.end_hour * 60 + att.end_min) - (att.start_hour * 60 + att.start_min)
        count = staff_counts.get(att.staff.id, 0)

        staff_data = StaffData(
            name=att.staff.name,
            level=att.staff.level,
            department=att.staff.department,
            start=att.start_hour,
            end=att.end_hour,
            shift_type=att.shift_type,
            count=count,
            work_minutes=work_minutes,
        )

        score = total_score(Slot(slot.start_hour, slot.end_hour), staff_data)

        # 3回目以降は選択可能だが大幅減点
        if count >= 2:
            score -= 5000

        staff_list.append({
            'id': att.staff.id,
            'name': att.staff.name,
            'level': att.staff.level,
            'shift_type': att.shift_type,
            'count': count,
            'score': score,
        })

    staff_list.sort(key=lambda x: (-x['score'], x['count']))

    return JsonResponse({
        'slot_id': slot.id,
        'time': f"{slot.start_hour}:00-{slot.end_hour}:00",
        'current': slot.assigned_staff.name if slot.assigned_staff else None,
        'candidates': staff_list,
    })


@login_required
@require_POST
def assign_staff(request, slot_id):
    slot = get_object_or_404(RegisterSlot, id=slot_id)
    data = json.loads(request.body)
    staff_id = data.get('staff_id')

    previous_staff = slot.assigned_staff
    new_staff = get_object_or_404(Staff, id=staff_id) if staff_id else None

    EditHistory.objects.create(
        slot=slot,
        edited_by=request.user,
        previous_staff=previous_staff,
        new_staff=new_staff,
    )

    slot.assigned_staff = new_staff
    slot.last_edited_by = request.user
    slot.is_auto_generated = False
    slot.save()

    return JsonResponse({
        'success': True,
        'slot_id': slot.id,
        'new_staff': new_staff.name if new_staff else None,
        'edited_by': request.user.username,
        'edited_at': timezone.now().strftime('%H:%M'),
    })


def generate_slots_for_date(target_date: date, user) -> list:
    attendances = DailyAttendance.objects.filter(date=target_date).select_related('staff')

    staffs = []
    for att in attendances:
        work_minutes = (att.end_hour * 60 + att.end_min) - (att.start_hour * 60 + att.start_min)
        staffs.append(StaffData(
            name=att.staff.name,
            level=att.staff.level,
            department=att.staff.department,
            start=att.start_hour,
            end=att.end_hour,
            shift_type=att.shift_type,
            count=0,
            work_minutes=work_minutes,
        ))

    generated = generate_register_shift(staffs)

    created_slots = []
    for slot in generated:
        assigned = None
        if slot.assigned:
            try:
                assigned = Staff.objects.get(name=slot.assigned.name)
            except Staff.DoesNotExist:
                pass

        db_slot = RegisterSlot.objects.create(
            date=target_date,
            start_hour=slot.start,
            end_hour=slot.end,
            assigned_staff=assigned,
            is_auto_generated=True,
            last_edited_by=user,
        )
        created_slots.append(db_slot)

    return created_slots


@login_required
@require_POST
def regenerate_shift(request):
    data = json.loads(request.body)
    date_str = data.get('date')

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return JsonResponse({'error': '無効な日付'}, status=400)

    RegisterSlot.objects.filter(date=target_date).delete()
    generate_slots_for_date(target_date, request.user)

    return JsonResponse({'success': True})


@login_required
@require_POST
def add_daily_attendance(request):
    data = json.loads(request.body)

    try:
        target_date = date.fromisoformat(data['date'])
        staff = get_object_or_404(Staff, id=data['staff_id'])

        if DailyAttendance.objects.filter(date=target_date, staff=staff).exists():
            return JsonResponse({'error': '既に登録済みです'}, status=400)

        start_hour = data.get('start_hour', 10)
        start_min = data.get('start_min', 0)
        end_hour = data.get('end_hour', 19)
        end_min = data.get('end_min', 0)

        shift_type = '早' if start_hour < 11 else '遅'

        DailyAttendance.objects.create(
            date=target_date,
            staff=staff,
            start_hour=start_hour,
            start_min=start_min,
            end_hour=end_hour,
            end_min=end_min,
            shift_type=shift_type,
        )

        return JsonResponse({
            'success': True,
            'message': f'{staff.name}を追加しました。再生成ボタンでシフトに反映されます。'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def remove_daily_attendance(request):
    data = json.loads(request.body)

    try:
        target_date = date.fromisoformat(data['date'])
        staff = get_object_or_404(Staff, id=data['staff_id'])
        DailyAttendance.objects.filter(date=target_date, staff=staff).delete()
        return JsonResponse({'success': True, 'message': f'{staff.name}を削除しました。'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def update_attendance(request):
    data = json.loads(request.body)

    try:
        attendance = get_object_or_404(DailyAttendance, id=data['attendance_id'])
        attendance.start_hour = data.get('start_hour', attendance.start_hour)
        attendance.start_min = data.get('start_min', attendance.start_min)
        attendance.end_hour = data.get('end_hour', attendance.end_hour)
        attendance.end_min = data.get('end_min', attendance.end_min)
        attendance.shift_type = '早' if attendance.start_hour < 11 else '遅'
        attendance.save()

        return JsonResponse({'success': True, 'message': f'{attendance.staff.name}の出勤情報を更新しました。'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def delete_attendance(request):
    data = json.loads(request.body)

    try:
        attendance = get_object_or_404(DailyAttendance, id=data['attendance_id'])
        staff_name = attendance.staff.name
        attendance.delete()
        return JsonResponse({'success': True, 'message': f'{staff_name}を削除しました。'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def staff_list(request):
    staffs = Staff.objects.filter(is_active=True).order_by('id')
    dept_order = ['店長', '季節', '家電', '情報', '通信']
    staffs_by_dept = {}
    for dept in dept_order:
        dept_staffs = [s for s in staffs if s.department == dept]
        if dept_staffs:
            staffs_by_dept[dept] = dept_staffs

    return render(request, 'register/staff_list.html', {
        'staffs_by_dept': staffs_by_dept,
        'dept_order': dept_order,
    })


@login_required
def staff_add(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        level = int(request.POST.get('level', 2))
        department = request.POST.get('department', '季節')

        if not name:
            messages.error(request, '名前を入力してください')
            return redirect('staff_add')

        if Staff.objects.filter(name=name).exists():
            messages.error(request, 'その名前は既に登録されています')
            return redirect('staff_add')

        Staff.objects.create(name=name, level=level, department=department)
        messages.success(request, f'{name}を追加しました')
        return redirect('staff_list')

    return render(request, 'register/staff_add.html', {
        'departments': Staff.DEPARTMENT_CHOICES,
        'levels': Staff.LEVEL_CHOICES,
    })


@login_required
def staff_edit(request, staff_id):
    from django.db import IntegrityError

    staff = get_object_or_404(Staff, id=staff_id)

    if request.method == 'POST':
        new_name = request.POST.get('name', '').strip()
        new_level = int(request.POST.get('level', 2))
        new_department = request.POST.get('department', '季節')

        if not new_name:
            messages.error(request, '名前を入力してください')
            return render(request, 'register/staff_edit.html', {
                'staff': staff,
                'departments': Staff.DEPARTMENT_CHOICES,
                'levels': Staff.LEVEL_CHOICES,
            })

        if Staff.objects.filter(name=new_name, is_active=True).exclude(id=staff_id).exists():
            messages.error(request, f'「{new_name}」は既に登録されています')
            return render(request, 'register/staff_edit.html', {
                'staff': staff,
                'departments': Staff.DEPARTMENT_CHOICES,
                'levels': Staff.LEVEL_CHOICES,
            })

        Staff.objects.filter(name=new_name, is_active=False).exclude(id=staff_id).delete()

        try:
            staff.name = new_name
            staff.level = new_level
            staff.department = new_department
            staff.save()
            messages.success(request, f'{staff.name}を更新しました')
            return redirect('staff_list')
        except IntegrityError:
            messages.error(request, '更新に失敗しました。名前が重複している可能性があります。')
            return render(request, 'register/staff_edit.html', {
                'staff': staff,
                'departments': Staff.DEPARTMENT_CHOICES,
                'levels': Staff.LEVEL_CHOICES,
            })

    return render(request, 'register/staff_edit.html', {
        'staff': staff,
        'departments': Staff.DEPARTMENT_CHOICES,
        'levels': Staff.LEVEL_CHOICES,
    })


@login_required
@require_POST
def staff_delete(request, staff_id):
    staff = get_object_or_404(Staff, id=staff_id)
    staff.is_active = False
    staff.save()
    return JsonResponse({'success': True})


@login_required
@require_POST
def staff_bulk_level(request):
    try:
        data = json.loads(request.body)
        staff_ids = data.get('staff_ids', [])
        new_level = data.get('level')

        if not staff_ids:
            return JsonResponse({'success': False, 'error': 'スタッフが選択されていません'})
        if new_level is None or new_level not in [0, 1, 2, 3, 4]:
            return JsonResponse({'success': False, 'error': '無効なレベルです'})

        updated = Staff.objects.filter(id__in=staff_ids, is_active=True).update(level=new_level)
        return JsonResponse({'success': True, 'updated': updated})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def shift_upload(request):
    import os
    import calendar
    from datetime import datetime

    result = None
    error = None

    if request.method == 'POST':
        uploaded_file = request.FILES.get('shift_file')
        year = int(request.POST.get('year', datetime.now().year))
        month = int(request.POST.get('month', datetime.now().month))

        if not uploaded_file:
            error = 'ファイルを選択してください'
        elif not uploaded_file.name.endswith(('.xlsx', '.xls')):
            error = 'Excelファイル(.xlsx, .xls)を選択してください'
        else:
            temp_path = f'/tmp/shift_upload_{datetime.now().strftime("%Y%m%d%H%M%S")}.xlsx'
            try:
                with open(temp_path, 'wb') as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

                from .shift_parser import import_shift_to_db
                result = import_shift_to_db(temp_path, year, month)

            except Exception as e:
                error = f'エラーが発生しました: {str(e)}'
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    current_year = datetime.now().year

    return render(request, 'register/shift_upload.html', {
        'result': result,
        'error': error,
        'years': list(range(current_year - 1, current_year + 2)),
        'months': list(range(1, 13)),
        'current_year': current_year,
        'current_month': datetime.now().month,
    })


@login_required
def shift_preview(request):
    import os
    from datetime import datetime

    preview_data = None
    error = None

    if request.method == 'POST':
        uploaded_file = request.FILES.get('shift_file')
        year = int(request.POST.get('year', datetime.now().year))
        month = int(request.POST.get('month', datetime.now().month))
        preview_date = request.POST.get('preview_date')

        if not uploaded_file:
            error = 'ファイルを選択してください'
        else:
            temp_path = f'/tmp/shift_preview_{datetime.now().strftime("%Y%m%d%H%M%S")}.xlsx'
            try:
                with open(temp_path, 'wb') as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

                from .shift_parser import parse_shift_excel
                all_data, all_staff = parse_shift_excel(temp_path, year, month)

                target = date.fromisoformat(preview_date) if preview_date else date(year, month, 1)

                preview_data = {
                    'date': target,
                    'attendances': all_data.get(target, []),
                    'total_days': len(all_data),
                }

            except Exception as e:
                error = f'エラーが発生しました: {str(e)}'
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    return JsonResponse({'preview': preview_data, 'error': error})
