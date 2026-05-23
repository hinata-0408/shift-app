"""
テストデータ投入スクリプト
使い方: python manage.py shell < setup_test_data.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from datetime import date
from register.models import Staff, DailyAttendance

# 名前, レベル, シフト種別（0=休み）
raw_data = """
店長
スタッフA,4,早
季節
スタッフB,4,早
スタッフC,4,0
スタッフD,4,中1
スタッフE,3,遅
スタッフF,3,遅
スタッフG,2,早
スタッフH,3,0
スタッフI,2,0
スタッフJ,2,0
スタッフK,1,0
スタッフL,1,0
家電
スタッフM,4,0
スタッフN,4,遅
スタッフO,3,早
スタッフP,3,早
スタッフQ,3,早
スタッフR,4,0
スタッフS,2,0
スタッフT,2,0
スタッフU,3,0
スタッフV,3,0
スタッフW,1,0
スタッフX,1,15遅
スタッフY,1,0
スタッフZ,0,0
情報
スタッフAA,4,遅
スタッフAB,3,遅
スタッフAC,4,0
スタッフAD,1,0
スタッフAE,2,早18
スタッフAF,2,0
スタッフAG,2,0
スタッフAH,1,0
スタッフAI,2,流早
スタッフAJ,1,0
スタッフAK,0,0
スタッフAL,0,0
通信
スタッフAM,4,0
スタッフAN,3,早
スタッフAO,3,1018
スタッフAP,3,0
スタッフAQ,2,0
スタッフAR,2,遅
スタッフAS,3,0
スタッフAT,2,0
スタッフAU,2,0
スタッフAV,2,0
スタッフAW,1,0
スタッフAX,2,0
スタッフAY,1,0
スタッフAZ,1,0
スタッフBA,3,0
スタッフBB,0,0
スタッフBC,2,遅
スタッフBD,0,1019
スタッフBE,1,0
"""


def parse_shift(shift_str):
    shift_str = shift_str.strip()

    if shift_str in ['0', '応', '応援', '会', '会議', '']:
        return None
    if shift_str == '早':
        return (9, 30, 19, 0, '早')
    if shift_str == '遅':
        return (11, 0, 20, 30, '遅')
    if shift_str == '中1':
        return (10, 0, 19, 0, 'その他')
    if shift_str == '流早':
        return (9, 30, 19, 0, '流早')
    if shift_str == '15遅':
        return (15, 0, 20, 30, '遅')
    if shift_str == '早18':
        return (9, 30, 18, 0, '早')

    if shift_str.isdigit():
        if len(shift_str) == 4:
            start = int(shift_str[:2])
            end = int(shift_str[2:])
            return (start, 0, end, 0, '早' if start <= 10 else '遅')
        elif len(shift_str) == 5:
            start = int(shift_str[:2])
            end = int(shift_str[2:4])
            return (start, 0, end, 0, '早' if start <= 10 else '遅')

    print(f"  未知のシフト形式: {shift_str}")
    return None


def main():
    DailyAttendance.objects.all().delete()
    Staff.objects.all().delete()

    current_department = None
    staff_list = []
    attendance_list = []
    today = date.today()

    for line in raw_data.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        if line in ['店長', '季節', '家電', '情報', '通信']:
            current_department = line
            continue

        parts = line.split(',')
        if len(parts) != 3:
            continue

        name, level, shift = parts
        level = int(level)

        staff = Staff(name=name, level=level, department=current_department or 'その他')
        staff_list.append(staff)

        shift_info = parse_shift(shift)
        if shift_info:
            start_h, start_m, end_h, end_m, shift_type = shift_info
            attendance_list.append({
                'name': name,
                'start_hour': start_h, 'start_min': start_m,
                'end_hour': end_h, 'end_min': end_m,
                'shift_type': shift_type,
            })

    Staff.objects.bulk_create(staff_list)
    print(f"{len(staff_list)} 名のスタッフを作成しました")

    for att in attendance_list:
        staff = Staff.objects.get(name=att['name'])
        DailyAttendance.objects.create(
            date=today, staff=staff,
            start_hour=att['start_hour'], start_min=att['start_min'],
            end_hour=att['end_hour'], end_min=att['end_min'],
            shift_type=att['shift_type'],
        )
    print(f"{len(attendance_list)} 件の出勤データを作成しました（{today}）")


if __name__ == '__main__':
    main()
