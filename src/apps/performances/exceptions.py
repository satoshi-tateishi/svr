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


class ZeroCostWarning(Exception):
    """
    外注車輌の原価が 0 円のまま Lock しようとした場合に raise する例外。

    LockService.lock_vehicle_operation が外注割当の applied_cost_amount == 0 を検知したとき、
    force=False（デフォルト）の場合に raise する。
    管理者が意図的に 0 円で確定する場合は force=True を指定して再実行する。
    """
