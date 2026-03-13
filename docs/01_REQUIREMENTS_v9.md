# REQUIREMENTS_v9.md

## 現行実装に合わせた最小要件

本書は、2026-03-13 時点のコードベースに合わせて「実装済み」「未実装」を明確にした要件整理です。

## 1. システム目的

最優先:

- 人員申請・車両申請・工程管理の入力負荷を下げる
- 手配ミスの温床になる情報分散を減らす

次点:

- ダブルブッキング防止
- Lock 済み実績の固定
- PDF 帳票の即時出力

将来課題:

- SaaS 連携
- 監査ログ基盤
- 横断分析の高度化

## 2. システム責務

### productions が担うもの

- 公演 (`Production`) の管理
- 工程ブロック / 工程日 / 申請単位の管理
- 人員申請・車両申請の入力
- 車両手配状態の管理

### performances が担うもの

- 実績公演 (`Performance`) の管理
- 標準工程展開
- 人員 / 車輌の割当
- 単価・原価スナップショット
- Lock
- PDF 帳票出力
- 乖離ダッシュボード

## 3. 絶対遵守ルール

1. Lock 後は解除しない
2. `applied_*` は Lock 時点のスナップショットとして扱う
3. 単価履歴は上書きではなく期間追加で管理する
4. ビジネスロジックはサービス層へ置く
5. 権限判定は `productions/services/permissions.py` に集約する
6. HTMX 画面は成功時に `HX-Redirect` を返す
7. インライン CSS は使わず Tailwind CSS のみ使う

## 4. 現行データ構造

### 申請側

```text
Production
└─ Process
   ├─ ProcessDay
   │  ├─ StaffRequest
   │  └─ VehicleRequest
   └─ ProcessRequestUnit
      ├─ StaffRequest
      └─ VehicleRequest
```

### 実績側

```text
Performance
├─ Phase
│  └─ PhaseSlot
│     └─ StaffAssignment
├─ PerformanceFreelanceRate
└─ VehicleOperation
   └─ VehicleAssignment
```

## 5. 人員管理要件

### 申請

- `StaffRequest` は `ProcessDay` または `ProcessRequestUnit` に紐づく
- 数量は `quantity`
- `include_self` を保持する
- 時間帯は任意入力で、未入力時は工程時間を暗黙利用する運用

### 実績

- `StaffAssignment` は `PhaseSlot` に紐づく
- 占有時間 `occupied_start` / `occupied_end` を持つ
- Lock 時に以下を保存する
  - `applied_unit_price`
  - `applied_allowance_total`
  - `applied_total_amount`
  - `applied_position_name`
  - `locked_at`

## 6. 車両管理要件

### 申請

- `VehicleRequest` は `ProcessDay` または `ProcessRequestUnit` に紐づく
- `requested_vehicle`, `request_kind`, `date`, `requested_time`, `arrival_requested_time` を持つ
- ルートは `route_from`, `route_to`
- 荷役人数は `loading_qty`, `unloading_qty` と `*_include_self`

### 管理手配

- `productions.VehicleAssignment` は `VehicleRequest` と 1:1
- `assigned_vehicle`, `status`, `note` を持つ
- ステータスは `pending`, `reviewing`, `confirmed`

### 実績

- `performances.VehicleOperation` は requested/scheduled を分離する
- `performances.VehicleAssignment` は Lock 時に `applied_cost_amount` を固定する

## 7. ダブルブッキング要件

### 人員

- `AssignmentService.confirm_staff_assignment()` が重複時間帯を拒否する
- 判定は半開区間

### 車輌

- `AssignmentService.confirm_vehicle_assignment()` が `scheduled_start/end` ベースで重複を拒否する
- 外注車輌は重複チェック対象外

## 8. Lock 要件

### `LockService.lock_phase_slot()`

- `PhaseSlot` を `LOCKED` にする
- 各 `StaffAssignment` に単価スナップショットを保存する
- 単価未登録やポジション未設定は 0 円で確定する

### `LockService.lock_vehicle_operation()`

- `VehicleOperation` を `LOCKED` にする
- 各 `VehicleAssignment` の `applied_cost_amount` を確定する
- 外注車輌で原価 0 円なら `ZeroCostWarning` を送出する

## 9. 帳票要件

- `ReportService.generate_performance_report()` は金額非表示の公演手配書を出力する
- `ReportService.generate_financial_report()` は金額表示の手配実績証明書を出力する
- いずれも Lock 済みデータのみ対象とする

## 10. 非機能要件

- Django / Docker Compose / MySQL 8.4 / Redis
- 日本語 UI 前提
- Ruff チェックとフォーマット必須
- テストは Docker コンテナ内で実行する

## 11. 未実装項目

- AuditLog
- SaaS 連携
- `productions` と `performances` の自動データ連携
- Lock 理由入力フロー
