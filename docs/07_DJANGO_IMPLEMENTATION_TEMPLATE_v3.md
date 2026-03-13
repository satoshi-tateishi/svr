# Django 実装テンプレート

## 1. 現行ディレクトリ構成

```text
src/
├─ apps/
│  ├─ accounts/
│  │  ├─ middleware.py
│  │  ├─ models.py
│  │  └─ views.py
│  ├─ productions/
│  │  ├─ forms.py
│  │  ├─ mixins.py
│  │  ├─ models.py
│  │  ├─ services/
│  │  │  ├─ permissions.py
│  │  │  └─ permission_response.py
│  │  ├─ templates.py
│  │  └─ views.py
│  └─ performances/
│     ├─ exceptions.py
│     ├─ models/
│     │  ├─ base.py
│     │  ├─ staff.py
│     │  └─ vehicle.py
│     ├─ services/
│     │  ├─ assignment_service.py
│     │  ├─ dashboard_query_service.py
│     │  ├─ freelance_rate_service.py
│     │  ├─ lock_service.py
│     │  ├─ performance_service.py
│     │  ├─ phase_service.py
│     │  ├─ report_service.py
│     │  └─ vehicle_service.py
│     └─ views.py
└─ templates/
   ├─ productions/
   └─ performances/
```

## 2. 実装原則

### サービス層

- `performances` のビジネスロジックはサービス層へ置く
- `productions` はまだ View 主導の箇所が多いが、権限判定は `services/permissions.py` に集約

### UI

- `productions` は HTMX モーダル
- `performances` は通常画面 + PDF
- Tailwind CSS のみ使用

### Lock

- `LockService` のみが Lock 状態遷移を担う前提
- Unlock は設けない

## 3. 主要サービス

### `PhaseService`

- 10 工程を一括展開
- 既存工程がある場合は `ValidationError`
- 各工程に空の `PhaseSlot` を 1 件作成

### `AssignmentService`

- 人員と車輌のダブルブッキング防止
- `select_for_update()` を使った競合防止
- 外注車輌は重複判定から除外

### `FreelanceRateService`

- 単価履歴の取得と重複防止

### `LockService`

- `PhaseSlot` と `VehicleOperation` のスナップショット確定
- `applied_*` の確定

### `DashboardQueryService`

- 人員不足
- 時間乖離
- Lock 漏れ

### `ReportService`

- Lock 済みデータのみを PDF 化
- WeasyPrint を使用

## 4. 現行実装で存在しないもの

- `signals.py` による業務ロジック集約
- `selectors.py` モジュール
- `FinancialSnapshot` モデル
- AuditLog サービス

## 5. 新規実装時の配置方針

- 権限ロジック: `src/apps/productions/services/`
- 実績計算・Lock・帳票: `src/apps/performances/services/`
- View にロジックを足す前に既存サービスへ寄せられないか確認する
