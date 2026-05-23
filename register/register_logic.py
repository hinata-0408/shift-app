"""
🛒 レジシフト自動生成ロジック

ルール＆スコア仕様書に基づく実装
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import date


# ===== データ定義 =====

@dataclass
class StaffData:
    """スタッフの当日データ"""
    name: str
    level: int          # 0-4
    department: str
    start: int          # 出勤開始（時）
    end: int            # 退勤（時）
    shift_type: str     # 早 / 遅 / 流早 / 流遅 / 通し / その他
    count: int = 0      # 当日レジ回数
    work_minutes: int = 0  # 勤務時間（分）


@dataclass
class Slot:
    """時間枠"""
    start: int
    end: int
    assigned: Optional[StaffData] = None
    score: int = 0      # 割当時のスコア（デバッグ用）


# ===== スコア計算 =====

def base_score(staff: StaffData) -> int:
    """
    レベル×回数 基礎スコア
    
    | レベル | 1回目 | 2回目 |
    |--------|-------|-------|
    | Lv1    | 100   | 60    |
    | Lv2    | 80    | 20    |
    | Lv3    | 40    | -20   |
    | Lv4    | -200  | -200  |
    | Lv0    | 候補外 | 候補外 |
    """
    if staff.level == 1:
        return 100 if staff.count == 0 else 60
    if staff.level == 2:
        return 80 if staff.count == 0 else 20
    if staff.level == 3:
        return 40 if staff.count == 0 else -20
    if staff.level == 4:
        return -200
    return -9999  # Lv0


def time_score(slot: Slot, staff: StaffData) -> int:
    """
    時間帯スコア
    
    | 時間    | 早番 | 遅番 |
    |---------|------|------|
    | 10-11   | +20  | -10  |
    | 11-12   | +20  | -10  |
    | 12-13   | -10  | +20  |
    | 13-14   | -5   | +10  |
    | 14-15   | 0    | +5   |
    | 15以降  | 0    | 0    |
    """
    is_early = staff.shift_type.startswith("早") or staff.shift_type == "流早"
    is_late = staff.shift_type.startswith("遅") or staff.shift_type == "流遅"
    
    if slot.start in (10, 11):
        return 20 if is_early else (-10 if is_late else 0)
    if slot.start == 12:
        return 20 if is_late else (-10 if is_early else 0)
    if slot.start == 13:
        return 10 if is_late else (-5 if is_early else 0)
    if slot.start == 14:
        return 5 if is_late else 0
    return 0


def special_penalty(slot: Slot, staff: StaffData) -> int:
    """
    特殊ルール
    - 流早 × 10時：-1000（実質NG）
    """
    if staff.shift_type == "流早" and slot.start == 10:
        return -1000
    return 0


def short_shift_penalty(staff: StaffData) -> int:
    """
    短時間勤務者への2回目以降ペナルティ
    
    - 3時間以下: -35
    - 4時間以下: -25
    - 5時間以下: -5
    
    ※1回目は適用しない（count >= 1 の場合のみ）
    """
    if staff.count == 0:
        return 0
    
    hours = staff.work_minutes / 60
    
    if hours <= 3:
        return -30
    if hours <= 4:
        return -25
    if hours <= 5:
        return -5
    return 0


def total_score(slot: Slot, staff: StaffData) -> int:
    """総合スコア計算"""
    return (
        base_score(staff)
        + time_score(slot, staff)
        + special_penalty(slot, staff)
        + short_shift_penalty(staff)
    )


# ===== メインロジック =====

def generate_register_shift(staffs: List[StaffData], start_hour: int = 10, end_hour: int = 20) -> List[Slot]:
    """
    レジシフト自動生成
    
    判定方式:
    1. 各時間枠ごとに候補者全員のスコアを計算
    2. 最大スコアの人を採用
    3. 同点の場合：レジ回数が少ない人優先
    
    Args:
        staffs: 当日の出勤スタッフリスト
        start_hour: 開始時間（デフォルト10時）
        end_hour: 終了時間（デフォルト20時）
    
    Returns:
        割当済みSlotのリスト
    """
    slots = [Slot(h, h + 1) for h in range(start_hour, end_hour)]
    
    for slot in slots:
        # 候補者フィルタリング
        # - Lv0は除外
        # - 出勤時間内かチェック
        # - 2回以上は候補外
        candidates = [
            s for s in staffs
            if s.level != 0
            and s.start <= slot.start < s.end
            and s.count < 2
        ]
        
        if not candidates:
            continue
        
        # スコア順でソート（同点はレジ回数少ない順）
        best = max(
            candidates,
            key=lambda s: (total_score(slot, s), -s.count)
        )
        
        best.count += 1
        slot.assigned = best
        slot.score = total_score(slot, best)
    
    return slots


def get_candidates_with_scores(slot: Slot, staffs: List[StaffData]) -> List[Dict]:
    """
    指定枠の候補者とスコアを取得（UI用）
    
    Returns:
        [{'staff': StaffData, 'score': int, 'breakdown': {...}}, ...]
    """
    candidates = []
    
    for s in staffs:
        if s.level == 0:
            continue
        if not (s.start <= slot.start < s.end):
            continue
        if s.count >= 2:
            continue
            
        score = total_score(slot, s)
        breakdown = {
            'base': base_score(s),
            'time': time_score(slot, s),
            'special': special_penalty(slot, s),
        }
        
        candidates.append({
            'staff': s,
            'score': score,
            'breakdown': breakdown,
        })
    
    # スコア降順でソート
    candidates.sort(key=lambda x: (-x['score'], x['staff'].count))
    
    return candidates


# ===== Django連携用ヘルパー =====

def convert_from_model(staff_model, attendance_model) -> StaffData:
    """
    DjangoモデルからStaffDataに変換
    
    Args:
        staff_model: register.models.Staff
        attendance_model: register.models.DailyAttendance
    """
    return StaffData(
        name=staff_model.name,
        level=staff_model.level,
        department=staff_model.department,
        start=attendance_model.start_hour,
        end=attendance_model.end_hour,
        shift_type=attendance_model.shift_type,
        count=0,
    )


def generate_shift_for_date(target_date: date, staff_attendance_pairs: list) -> List[Slot]:
    """
    指定日のレジシフトを生成
    
    Args:
        target_date: 対象日
        staff_attendance_pairs: [(Staff, DailyAttendance), ...] のリスト
    
    Returns:
        割当済みSlotのリスト
    """
    staffs = [
        convert_from_model(staff, attendance)
        for staff, attendance in staff_attendance_pairs
    ]
    
    return generate_register_shift(staffs)


# ===== テスト用 =====

if __name__ == "__main__":
    # テストデータ
    test_staffs = [
        StaffData("田中", 1, "食品", 10, 15, "早"),
        StaffData("佐藤", 2, "食品", 10, 15, "早"),
        StaffData("鈴木", 2, "非食品", 13, 20, "遅"),
        StaffData("高橋", 3, "食品", 13, 20, "遅"),
        StaffData("渡辺", 4, "食品", 10, 20, "通し"),
        StaffData("伊藤", 0, "食品", 10, 15, "早"),  # Lv0は除外される
    ]
    
    slots = generate_register_shift(test_staffs)
    
    print("=== レジシフト自動生成結果 ===")
    for slot in slots:
        if slot.assigned:
            print(f"{slot.start}:00-{slot.end}:00 → {slot.assigned.name} (Lv{slot.assigned.level}, score={slot.score})")
        else:
            print(f"{slot.start}:00-{slot.end}:00 → 未割当")
