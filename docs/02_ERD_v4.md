# 公演手配管理システム ERD

## 1. 前提

現行実装は、申請系の `productions` と確定実績系の `performances` を別集約として保持しています。旧設計のような単一 `Performance` 中心 ERD ではありません。

## 2. エンティティ一覧

### accounts

- `User`
- `UserProfile`

### productions

- `Production`
- `ProductionHoliday`
- `ProcessType`
- `Position`
- `ProductionTemplate`
- `Process`
- `ProcessRequestUnit`
- `ProcessDay`
- `StaffRequest`
- `VehicleRequest`
- `VehicleAssignment`
- `ProductionMember`

### performances

- `Performance`
- `Phase`
- `PhaseSlot`
- `PerformancePosition`
- `PerformanceResponsibleStaff`
- `PhaseMaster`
- `PerformanceFreelanceRate`
- `StaffAssignment`
- `Vehicle`
- `VehicleOperation`
- `VehicleAssignment`

## 3. 関連図

### 3.1 申請系

```text
User ── 1:1 ── UserProfile

Production
├─ ProductionHoliday
├─ ProductionMember ── N:1 ── User
└─ Process
   ├─ ProcessDay
   │  ├─ StaffRequest ── N:1 ── Position
   │  └─ VehicleRequest ── N:1 ── performances.Vehicle
   └─ ProcessRequestUnit
      ├─ StaffRequest ── N:1 ── Position
      └─ VehicleRequest ── 1:1 ── performances.Vehicle

VehicleRequest ── 1:1 ── productions.VehicleAssignment ── N:1 ── performances.Vehicle
```

### 3.2 実績系

```text
Performance
├─ PerformanceResponsibleStaff ── N:1 ── User
├─ Phase
│  └─ PhaseSlot
│     └─ StaffAssignment ── N:1 ── User
│                       └─ N:1 ── PerformancePosition
├─ PerformanceFreelanceRate ── N:1 ── User / PerformancePosition
└─ VehicleOperation
   └─ performances.VehicleAssignment
      ├─ N:1 ── Vehicle
      └─ N:1 ── User(driver_user)
```

## 4. 主要モデル要約

### `Production`

- `code`, `title`, `created_by`
- `start_date`, `end_date` は仮期間
- 表示上の期間は `ProcessRequestUnit.work_date` または `ProcessDay.date` を優先

### `Process`

- `production` に従属
- `title`, `block_key`, `order`
- `unique_together = ['production', 'title']`

### `ProcessRequestUnit`

- 工程ブロック内の申請単位
- `unit_type` は `transport` / `staffing`
- `work_date`, `location`, `start_time`, `end_time`, `setup_label`

### `ProcessDay`

- 既存 UI 互換の工程日
- `process_type`, `date`, `location`, `start_time`, `end_time`

### `StaffRequest`

- `process_day` または `process_request_unit`
- `position`, `quantity`, `include_self`
- 任意の `start_time`, `end_time`

### `VehicleRequest`

- `process_day` または `process_request_unit`
- `requested_vehicle`, `request_kind`, `date`
- `requested_time`, `arrival_requested_time`
- `route_from`, `route_to`

### `productions.VehicleAssignment`

- `vehicle_request` と 1:1
- `assigned_vehicle`, `status`, `note`

### `Performance`

- `title`, `description`, `created_by`
- 申請系 `Production` とは別モデル

### `Phase` / `PhaseSlot`

- `Phase` は標準工程展開の単位
- `PhaseSlot` は人員枠
- `status = draft / assigned / locked`

### `StaffAssignment`

- `PhaseSlot` に属する実績人員割当
- `occupied_start`, `occupied_end`
- Lock 後スナップショットを `applied_*` に保持

### `VehicleOperation`

- requested / scheduled を分離
- `status = draft / assigned / locked`
- 論理削除用に `is_active`, `deleted_at`, `deleted_by` を持つ

### `performances.VehicleAssignment`

- `VehicleOperation` に属する実績配車割当
- `applied_cost_amount`, `applied_sales_amount`, `locked_at`

## 5. 不変条件

- Lock 済み `PhaseSlot` / `VehicleOperation` は解除しない
- `PerformanceFreelanceRate` は期間追加で履歴管理する
- 申請値 (`requested_*`) は確定値 (`scheduled_*`) で上書きしない
- `productions` と `performances` は現時点で疎結合
