"""
performances アプリ固有の例外定義
"""


class ConflictError(Exception):
    """
    ダブルブッキング（時間重複）を検出した場合に raise する例外。

    AssignmentService の confirm_staff_assignment / confirm_vehicle_assignment が
    占有時間の重複を検知したときに使用する。
    DB への保存は行われない（raise される前にトランザクションがロールバックされる）。
    """
