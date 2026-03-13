# 監査ログ設計書

## 1. 現状

2026-03-13 時点で、専用の `AuditLog` モデルおよび永続化ロガーは未実装です。旧版ドキュメントにある監査ログ仕様は将来設計であり、現行コードの事実ではありません。

## 2. 既に存在する証跡

### アプリケーションログ

- `performances.views` でテンプレート展開や工程追加などを `logger.info()` / `logger.warning()` に出力
- `accounts.middleware` で JWT 認証結果や同期エラーをログ出力

### DB スナップショット

監査ログの代替ではありませんが、以下は事実上の証跡です。

- `StaffAssignment.applied_*`, `locked_at`
- `performances.VehicleAssignment.applied_cost_amount`, `locked_at`
- `PhaseSlot.status`
- `VehicleOperation.status`
- `VehicleOperation.deleted_at`, `deleted_by`, `updated_by`

## 3. 将来 AuditLog を入れる場合の最低対象

- Portal JWT 自動リンク / 自動作成
- `PhaseService.apply_production_template()`
- `AssignmentService.confirm_staff_assignment()`
- `AssignmentService.confirm_vehicle_assignment()`
- `LockService.lock_phase_slot()`
- `LockService.lock_vehicle_operation()`
- PDF 出力
- `productions.VehicleAssignment` の状態変更

## 4. 現行実装に合わせた方針

AuditLog を追加する場合も、以下は変えない。

1. Lock 後データは再計算しない
2. 金額参照は `applied_*` を基準にする
3. HTMX / 通常 POST の両方で同じイベント語彙を使う

## 5. 未実装として明示しておく事項

- `before_state` / `after_state` JSON
- `snapshot_hash`
- Unlock 記録
- Drift 理由の強制入力
- スプレッドシートエクスポート
