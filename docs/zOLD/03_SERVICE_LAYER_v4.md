# SERVICE_LAYER_v4.md

## 公演手配管理システム サービス層設計書（人員・配車・テンプレート統合版）

* * *

# 1. 設計目的

Service層の目的：

-   演劇制作の標準工程（1〜9のテンプレート）の一括生成
-   🔒 Lock時の「人員単価」と「車輌原価」の同時スナップショット確定
-   **「希望（Request） vs 確定（Assignment）」** の乖離（人数・時間）の可視化
-   トランザクション境界の明確化とLock後不変性の徹底

* * *

# 2. サービス分類（最終版）

1.  **PerformanceService**: 公演全体の管理
2.  **PhaseService**: テンプレート展開（仕込・稽古・本番・バラシ等）
3.  **PhaseSlotService**: 人員枠（Request/Assignment）および占有時間管理
4.  **VehicleOperationService**: 運行工程（希望時間 vs 確定時間）管理
5.  **VehicleService**: 車輌マスタおよび変動原価（外注費・距離）管理
6.  **AssignmentService**: 人員・車輌の紐付けと重複チェック
7.  **FreelanceRateService**: 単価履歴管理
8.  **AllowanceService**: 手当管理
9.  🔒 **LockService**: 全実績のスナップショット確定（最重要）
10.  **ApiIntegrationService / DashboardQueryService / AuditLogService**
11.  **StaffRequestService**: 人員手配の一括編集・コピー管理（New）

* * *

# 3. 各サービス詳細

## 3.1 PhaseService（テンプレート制御）
...
## 3.10 ApiIntegrationService / DashboardQueryService / AuditLogService
...
* * *

## 3.11 StaffRequestService（人員手配一括操作）

**責務**: `ProcessDay` 単位での複数人員手配の整合性管理と操作。

-   **bulk_update_requests(day_id, requests_json)**:
    
    -   既存の手配を削除・更新し、JSONベースで一括登録する。
    -   同一ポジションの重複禁止チェックを行う。
-   **get_previous_day_requests(day_id)**:
    
    -   同一 Production 内で過去の直近日付の `StaffRequest` を検索して返す。
    -   コピー元の日付 (`source_date`) を特定する。

**責務**: 演劇の標準フローに基づき、案件の骨子を一括作成する。

### apply_production_template(performance_id, start_date)

以下の工程を `Phase` およびデフォルトの `PhaseSlot` として一括生成する：

1.  機材作り / 2. 稽古場仕込み / 3. 稽古 / 4. 稽古場バラシ / 5. 劇場仕込み / 6. 舞台稽古 / 7. 本番 / 8. 劇場バラシ / 9. ツアー・最終荷降ろし

* * *

## 3.2 PhaseSlotService（人員要求・枠）

**責務**: 「いつ、何人必要か」の枠（Slot）を管理。

-   **calculate_occupied_time(slot)**: 集合〜解散にバッファを加えた占有時間を算出。
-   **update_request_count(slot_id, count)**: 希望人数の設定。

* * *

## 3.3 VehicleOperationService（配車工程・時間比較）

**責務**: 運行の「希望」と「実態」を管理。

-   **create_operation(performance_id, data)**: 制作からの配車依頼。`requested_start/end` を保持。
-   **confirm_schedule(operation_id, data)**: 管理者による配車確定。`scheduled_start/end` を保持。

* * *

## 3.4 VehicleService（車輌・コスト）

**責務**: 車輌種別に応じた原価管理。

-   **calculate_preliminary_cost(vehicle_id, distance)**: 距離に応じた暫定原価算出。
-   **finalize_vehicle_cost(assignment_id, amount)**: Lock直前に管理者が確定原価を手動入力。

* * *

## 3.5 AssignmentService（共通割当）

**責務**: 人員・車輌の紐付け。

-   **confirm_assignment(slot_id, user_id, vehicle_id)**:
    
    -   `ScheduleConflictService` で人員・車輌双方の重複を検証。
    -   重複がなければ `StaffAssignment` / `VehicleAssignment` を作成。

* * *

# 4. 🔒 LockService（最重要：スナップショット確定）

**責務**: Slot（人員）またはOperation（配車）を Locked に遷移させ、全金額を固定する。

### lock_execution(unit_id, type=['staff', 'vehicle'])

`@transaction.atomic` 下で実行。

1.  **Target select_for_update**: 対象の Slot/Operation をロック。
2.  **Staff Snapshot**:
    
    -   `FreelanceRateService.get_applicable_rate()` で単価取得。
    -   `applied_unit_price`, `applied_allowance_total`, `applied_total_amount` を保存。
3.  **Vehicle Snapshot**:
    
    -   その時点の確定原価（applied_cost_amount）と請求額（applied_sales_amount）を保存。
4.  **Metadata Snapshot**:
    
    -   その時のポジション名、確定工程数、`locked_at` を記録。
5.  **Status Update**: `status = Locked` へ遷移。

* * *

# 5. DashboardQueryService（乖離分析）

**責務**: 申請と実態の差分を抽出し、管理者に警告を出す。

-   **get_staffing_shortages()**: `requested_staff_count > actual_staff_count` のリスト。
-   **get_schedule_drifts()**: `requested_time` と `scheduled_time` が30分以上乖離している工程。
-   **get_unlocked_past_slots()**: 日時が過ぎているが Locked になっていない項目の抽出。

* * *

# 6. 設計思想の厳守事項

1.  **Lock後の不可逆性**: Lock解除APIは作成しない。修正が必要な場合は「調整用レコード」を新規作成する。
2.  **時間の上書き禁止**: 希望時間（Requested）を確定時間（Scheduled）で上書きせず、両方を保持して比較可能にする。
3.  **SaaS連携**: `ApiIntegrationService` は必ず `applied_` で始まるスナップショット項目のみを参照して送信データを生成する。



