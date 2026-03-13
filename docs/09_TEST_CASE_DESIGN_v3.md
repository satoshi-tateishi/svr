# テストケース詳細設計書

## 1. 現在の重点対象

現行実装に照らして優先度が高いのは次の領域です。

1. Portal JWT 認証とユーザー同期
2. `productions` の一括編集 UI
3. `performances` のテンプレート展開
4. ダブルブッキング防止
5. Lock と PDF

## 2. `performances` サービス

### `PhaseService`

- 工程数が 10 件で生成される
- 二重展開が拒否される
- 各 `Phase` に `PhaseSlot` が 1 件作成される

### `AssignmentService`

- 人員重複が拒否される
- 車輌重複が拒否される
- 外注車輌は重複チェック除外になる

### `LockService`

- `lock_phase_slot()` で `PhaseSlot.status` が `LOCKED` になる
- `StaffAssignment.applied_*` が保存される
- `lock_vehicle_operation()` で `VehicleOperation.status` が `LOCKED` になる
- 外注原価 0 円時は `ZeroCostWarning`

### `ReportService`

- Lock 済みデータがなければ `ValidationError`
- 公演手配書は金額を出さない
- 手配実績証明書は `applied_*` から金額集計する

### `DashboardQueryService`

- 人員不足抽出
- 時間乖離抽出
- Lock 漏れ抽出

## 3. `productions` View

### `StaffRequestBulkEditView`

- `requests_json` の JSON 形式不正で再描画
- 数量 0 以下でエラー
- 終了時間のみ入力でエラー
- 開始時間 >= 終了時間でエラー
- 正常保存時は `HX-Redirect`

### `VehicleRequestBulkEditView`

- `requests_json` の JSON 形式不正で再描画
- 不正な車両 ID を拒否
- 正常保存時は `HX-Redirect`
- 前日コピー API が期待 JSON を返す

### 権限 Mixins

- HTMX 時は HTML 403
- 通常リクエスト時は通常 403
- `admin/editor` と `ProductionMember` の差を確認する

## 4. Portal JWT

- `sub` 一致で既存プロフィールへログイン
- email 一致で `portal_uuid` 自動リンク
- 未登録なら新規作成
- 無効トークンは認証しない

## 5. 未実装前提で除外する項目

以下は旧版の想定だったが、現行テスト設計から外す。

- `FinancialSnapshot`
- 監査ログの `before_state/after_state`
- Unlock
- Drift 理由入力必須
