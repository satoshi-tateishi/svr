# PROJECT_CONTEXT

## 目的

`svr` は、演劇制作の申請整理と管理側の確定運用を支える Django ベースの業務システムです。
現在は次の 2 ドメインを明確に分けて実装しています。

- `productions`: 申請入力、工程ブロック管理、公演担当者管理、車両手配 UI
- `performances`: 実績公演、標準工程、人員割当、車輌運行、Lock、原価スナップショット、乖離抽出

重要な前提:

- `Production` と `Performance` は別モデルであり、自動同期しません
- 現在のユーザー向け UI の中心は `productions`
- `performances` はサービス層とモデルが整っている一方、公開画面は限定的です

## 現在の公開導線

URL 実装の現状は次の通りです。

- `/` は `/productions/dashboard/` にリダイレクト
- `/auth/` は Portal SSO 用導線
- `/productions/` は公演一覧・公演詳細・工程ブロック編集・車両手配管理
- `/performances/` は独立 UI を持たず、`/productions/dashboard/` にリダイレクト

つまり、以前の設計資料にある「`/performances/dashboard/` が主導線」という前提は現行コードでは正しくありません。
乖離ダッシュボード自体は `performances.services.dashboard_query_service` を使っていますが、画面実装は `productions.views.dashboard` にあります。

## 技術スタック

- Django
- MySQL 8.4
- Redis
- Docker Compose
- HTMX
- Alpine.js
- Tailwind CSS
- WhiteNoise

設定上の特徴:

- `TIME_ZONE = 'Asia/Tokyo'`
- セッションは Redis キャッシュを使用
- 静的配信は WhiteNoise
- Python コード品質は `ruff check` / `ruff format`

## アプリ別の責務

### accounts

認証・プロフィール管理を担当します。

- `UserProfile` が Portal 連携情報と全体権限を保持
- `PortalJWTMiddleware` が `portal_jwt` クッキーを検証
- JWT の `sub` を `portal_uuid` として `UserProfile` に紐付け
- 未登録時は email で既存 `User` を探索し、なければ自動作成

`UserProfile.system_role` の選択肢:

- `admin`
- `editor`
- `general`
- `viewer`

注意点:

- 新規作成直後のプロフィール参照は `user.profile` 前提
- `post_save(User)` で `UserProfile` が自動作成される

### productions

現行 UI の中心です。申請入力と管理系画面の多くがここにあります。

主要責務:

- `Production` の一覧、作成、編集、詳細表示
- `ProductionMember` による公演担当者管理
- `Process` 単位の工程ブロック管理
- `ProcessRequestUnit` 単位の申請編集
- `StaffRequest` と `VehicleRequest` の入力
- 管理側 `productions.VehicleAssignment` による車両手配
- ダッシュボード表示

現行の構造上の重要点:

- 申請編集は `ProcessDay` よりも `ProcessRequestUnit` 中心へ寄っています
- ただし `ProcessDay` はまだ残っており、旧系データ互換や一部参照に使われています
- `VehicleRequest` は `process_day` と `process_request_unit` の両方を参照可能です
- 管理側車両手配 `productions.VehicleAssignment` は `VehicleRequest` ごとに 1 件です

### performances

実績・確定系ドメインです。公開ビューはほぼありませんが、サービス層はこのアプリにあります。

主要責務:

- `Performance`
- `Phase` / `PhaseSlot`
- `StaffAssignment`
- `PerformanceFreelanceRate`
- `Vehicle`
- `VehicleOperation`
- `performances.VehicleAssignment`
- ダブルブッキング防止
- Lock による `applied_*` スナップショット保存
- 乖離 / 不足 / Lock 漏れ抽出

現状:

- `/performances/` 配下の CRUD 画面は未公開
- ただしモデル、サービス、例外、管理コマンドは実装済み
- `productions` 側ダッシュボードから `performances` サービスを利用しています

## ドメインモデルの理解

### productions 側

主要モデル:

- `Production`: 公演案件の基礎情報
- `ProductionHoliday`: 休演日
- `ProcessType`: 工程種別マスタ
- `Position`: 申請ポジションマスタ
- `ProductionTemplate`: 工程テンプレート JSON
- `Process`: 工程ブロック
- `ProcessRequestUnit`: ブロック内の申請単位
- `ProcessDay`: 旧来の工程タスク単位
- `StaffRequest`: 人員申請
- `VehicleRequest`: 車両申請
- `productions.VehicleAssignment`: 管理側車両手配
- `ProductionMember`: 公演担当者

`ProcessRequestUnit` の `unit_type`:

- `transport`: 車両便申請
- `staffing`: 人員申請

ここが現在の UI 設計の要です。1 つの工程ブロックの中で、「車両便」と「人員申請」を別単位として分離して扱います。

`VehicleRequest` の特徴:

- 申請車両 `requested_vehicle` は `performances.Vehicle` を参照
- `requested_time` と `arrival_requested_time` を保持
- `loading_qty` / `unloading_qty` と `include_self` で荷役人数も申請
- `effective_date` は `date` → `process_request_unit.work_date` → `process_day.date` の順で決まる

`productions.VehicleAssignment` の特徴:

- `VehicleRequest` と 1:1
- `assigned_vehicle` は `performances.Vehicle`
- `arranged_departure_time` と `arranged_arrival_time` を分離保持
- 管理状態は `pending` / `reviewing` / `confirmed`

### performances 側

主要モデル:

- `Performance`: 実績公演
- `Phase`: 工程
- `PhaseSlot`: 人員枠
- `PerformancePosition`: 実績側ポジションマスタ
- `PerformanceResponsibleStaff`: 公演担当者
- `PhaseMaster`: 工程マスタ
- `PerformanceFreelanceRate`: 単価履歴
- `StaffAssignment`: 人員割当
- `Vehicle`: 車輌マスタ
- `VehicleOperation`: 運行工程
- `performances.VehicleAssignment`: 配車割当

`Phase` について:

- 現行コードは `PhaseService.TEMPLATE_STEPS` で **10 工程** を標準とします
- `Phase` モデルの docstring に「1〜9」とある箇所は古く、実装の真実ではありません

標準 10 工程:

1. 機材作り
2. 稽古場仕込み
3. 稽古
4. 稽古場バラシ
5. 劇場仕込み
6. 舞台稽古
7. 本番
8. 劇場バラシ
9. ツアー
10. 最終荷降ろし

`StaffAssignment` の特徴:

- 占有時間 `occupied_start` / `occupied_end` を保持
- Lock 時に `applied_unit_price` などをスナップショット保存

`VehicleOperation` の特徴:

- 希望値 `requested_*` と確定値 `scheduled_*` を分離
- 希望値は上書きせず、乖離分析の基準に使う
- 論理削除用の `is_active`, `deleted_at`, `deleted_by` を持つ

`performances.VehicleAssignment` の特徴:

- `VehicleOperation` に対する実績側の配車割当
- Lock 時に `applied_cost_amount` / `applied_sales_amount` を保持

## サービス層の実態

### productions 側

明確にサービス化されているのは権限判定です。

- `src/apps/productions/services/permissions.py`
- `src/apps/productions/services/permission_response.py`

権限判定は View に直書きせず、ここへ寄せる方針です。

### performances 側

サービス層がドメインの中心です。

- `phase_service.py`: 10 工程テンプレート展開
- `assignment_service.py`: 人員・車輌の割当確定と競合防止
- `freelance_rate_service.py`: 単価履歴解決
- `lock_service.py`: Lock と `applied_*` 確定
- `dashboard_query_service.py`: 不足・乖離・Lock 漏れ抽出
- `performance_service.py`: 実績公演 CRUD 用サービス
- `vehicle_service.py`: 車輌マスタ・運行工程関連

重要な業務ルール:

- Lock は不可逆
- Lock 済みの Slot / Operation を解除しない
- 修正は調整用レコード追加で吸収する前提
- PDF や外部連携や集計は `applied_*` を参照する

## 権限モデル

権限は二層です。

全体権限:

- `UserProfile.system_role`

公演単位権限:

- `ProductionMember.role`

現行 `productions.services.permissions` のルール:

- `admin` / `editor` は申請編集・工程編集・車両手配管理が可能
- `general` / `viewer` は全体権限だけでは編集不可
- ただし `ProductionMember.role` が `sound_designer` または `chief` なら、その公演の申請編集・工程編集は可能
- 車両手配管理と原価閲覧は `admin` / `editor` のみ

## UI とテンプレート構成

テンプレートは次の 2 系統が中心です。

- `src/templates/productions/`: 公演一覧、公演詳細、工程ブロック編集、担当者編集
- `src/templates/production_management/`: ダッシュボード、車両手配一覧、日別レーン編集

現行 UI の特徴:

- HTMX モーダル主体
- 成功時は `HX-Redirect` または `HX-Refresh` を返す
- 権限エラー時は HTMX/通常リクエストを吸収するレスポンスを返す設計

工程ブロック編集の実態:

- 「車両便を追加」と「人員申請を追加」を別ボタンで扱う
- ブロック全体備考ではなく、申請単位ごとに `note` を持つ
- `travel_unload` など一部ブロックでは人員申請を禁止

車両手配 UI の実態:

- `productions:production_vehicle_assignments` は日付ごとの俯瞰画面
- `productions:production_vehicle_assignments_day_edit` は日別の車両レーン編集画面
- `VehicleAssignment` はアクセス時に不足分を自動生成する実装がある

## ダッシュボードの意味

`/productions/dashboard/` は `DashboardQueryService` を使って次を表示します。

- 人員不足: `requested_staff_count > actual_count`
- 時間乖離: `requested_start` と `scheduled_start` の差が閾値以上
- Lock 漏れ: 過去日付なのに `PhaseSlot.status != LOCKED`

このため、画面は `productions` にありますが、分析対象データは `performances` 側です。

## 認証フロー

`PortalJWTMiddleware` の実装フロー:

1. `portal_jwt` クッキーを取得
2. JWKS で署名検証
3. `sub` を `portal_uuid` として `UserProfile` を検索
4. なければ email で既存 `User` を検索しリンク
5. それもなければ `User` を自動作成
6. Django セッションへ `login()`

設定値:

- `PORTAL_JWKS_URL`
- `PORTAL_JWT_ISSUER`
- `PORTAL_JWT_AUDIENCE`
- `PORTAL_LOGIN_URL`

## 現状の実装済み / 未実装

実装済み:

- Portal JWT 連携
- `productions` の公演一覧・作成・編集・詳細
- 公演担当者管理
- 工程ブロック編集
- `ProcessRequestUnit` ベースの人員申請 / 車両申請
- 管理側の車両手配一覧・日別編集
- `performances` のサービス層
- ダブルブッキング防止ロジック
- Lock と `applied_*` スナップショット
- 乖離ダッシュボード用クエリ

未実装または限定実装:

- `productions` と `performances` の自動同期
- `performances` の本格的な公開 CRUD 画面
- AuditLog 基盤
- SaaS 連携
- Celery 実運用
- PDF 出力の現行 UI 導線確認

## テストの把握ポイント

現行テストから読み取れる重要な事実:

- 生きている導線は `productions` 側が中心
- 公演一覧、詳細、編集モーダル、担当者モーダル、工程ブロックモーダルは稼働中
- 車両管理は公演別とダッシュボード別の両方が稼働中
- 工程ブロック編集は `ProcessRequestUnit` 構造を前提に検証されている

## ChatGPT 向けの最重要要約

このプロジェクトを把握するうえで最重要なのは次の点です。

- 現在の主戦場は `productions`
- ただし重要な業務ロジックは `performances.services` にある
- `Production` と `Performance` は別物で、自動同期しない
- `ProcessRequestUnit` が新しい申請編集の中心
- 車両の申請と管理手配は `productions` にある
- 実績・原価・Lock は `performances` にある
- Lock は不可逆で、確定後は `applied_*` を信頼する
- `/performances/` は現在独立画面ではなく、`/productions/dashboard/` に寄せられている
