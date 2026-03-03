# 12_PORTAL_INTEGRATION_GUIDE.md

## svr 実装進捗・引き継ぎガイド

`svr`（演劇制作人員・配車・工程管理システム）の実装状況と、
次回作業を再開するための情報をまとめたドキュメントです。

---

## 実装進捗

| フェーズ | 内容 | 状態 |
|---------|------|------|
| Week 1 | JWT 連携層・Docker 基盤構築 | ✅ 完了 |
| Week 2 | コアモデル・サービス層・テンプレート展開 | ✅ 完了 |
| Week 3 | ダブルブッキング防止（AssignmentService） | ✅ 完了 |
| Week 4 | 単価・原価管理 + 乖離分析 | ✅ 完了 |
| Week 5 | LockService + スナップショット確定 | 未着手 |
| Week 6 | PDF 帳票出力 | 未着手 |
| Week 7 | UI ブラッシュアップ + ダッシュボード | 未着手 |
| Week 8 | 本番デプロイ + SaaS 連携（freee/board） | 未着手 |

---

## 実装済みファイル一覧

### Week 1 — JWT 連携層・基盤

| ファイル | 内容 |
|---------|------|
| `src/apps/accounts/middleware.py` | PortalJWTMiddleware（JWT 検証・ユーザー自動作成） |
| `src/apps/accounts/models.py` | UserProfile（portal_uuid・JWT 同期フィールド・SystemRole） |
| `src/apps/accounts/views.py` | login_view / logout_view（Open Redirect 対策済み） |
| `src/apps/accounts/urls.py` | `/auth/login/`, `/auth/logout/` |
| `src/apps/accounts/admin.py` | Admin UI（JWT 同期フィールドは読み取り専用） |
| `src/config/settings.py` | Django 設定（PORTAL_JWKS_URL 等含む） |
| `src/config/urls.py` | URL ルーティング（auth / performances） |
| `docker-compose.yml` | shin-on-internal ネットワーク・svr_web（ポート 8085） |
| `.env.sample` | 環境変数サンプル |
| `Dockerfile` | Python 3.12-slim ベース |
| `pyproject.toml` | Ruff 設定（py312, line-length=100, single-quote, migrations除外） |

### Week 2 — コアモデル・サービス層・テンプレート展開

| ファイル | 内容 |
|---------|------|
| `src/apps/performances/models/base.py` | Performance / Phase / PhaseSlot / PerformancePosition |
| `src/apps/performances/models/staff.py` | StaffAssignment / PerformanceFreelanceRate（applied_* 先行定義） |
| `src/apps/performances/models/vehicle.py` | Vehicle / VehicleOperation（希望/確定分離）/ VehicleAssignment |
| `src/apps/performances/services/phase_service.py` | **最重要** テンプレート展開（9工程一括・冪等性ガード付き） |
| `src/apps/performances/services/performance_service.py` | 公演 CRUD |
| `src/apps/performances/services/vehicle_service.py` | 車輌マスタ・運行工程（confirm_schedule で希望値を保持） |
| `src/apps/performances/services/freelance_rate_service.py` | 単価履歴（期間重複禁止・ValidationError） |
| `src/apps/performances/admin.py` | Django Admin UI（VehicleOperation の乖離表示含む） |
| `src/apps/performances/views.py` | 公演一覧・作成・詳細・テンプレート展開 POST |
| `src/apps/performances/urls.py` | performances URL ルーティング |
| `src/templates/performances/*.html` | Tailwind CSS UI（一覧・作成・詳細） |
| `src/apps/performances/tests/test_phase_service.py` | PhaseService テスト 9 ケース |
| `src/apps/performances/tests/test_models.py` | モデルテスト |

### Week 3 — ダブルブッキング防止（AssignmentService）

| ファイル | 内容 |
|---------|------|
| `src/apps/performances/exceptions.py` | `ConflictError`（ダブルブッキング用カスタム例外） |
| `src/apps/performances/services/assignment_service.py` | **最重要** 重複チェック付き人員・車輌割当 |
| `src/apps/performances/tests/test_assignment_service.py` | 重複チェックのテスト 12 ケース（全 PASSED） |
| `src/config/settings_test.py` | テスト用設定（インメモリ SQLite・LocMemCache） |
| `requirements.txt` | pytest / pytest-django を追加 |
| `pyproject.toml` | `DJANGO_SETTINGS_MODULE` を `config.settings_test` に変更 |

#### Week 3 で実装した仕様メモ

```
AssignmentService.confirm_staff_assignment(slot, user, occupied_start, occupied_end, position=None)
  ├─ select_for_update() で対象スタッフの割当レコードを行ロック
  ├─ 半開区間 [occupied_start, occupied_end) で重複チェック
  │    条件: existing.occupied_start < new.occupied_end
  │          AND existing.occupied_end > new.occupied_start
  └─ 重複あり → ConflictError を raise（DB 保存なし）

AssignmentService.confirm_vehicle_assignment(operation, vehicle, driver_user=None, is_external_driver=False)
  ├─ vehicle.is_external == True → チェックをスキップ（外注車輌は複数工程割当が前提）
  ├─ operation.scheduled_start/end が None → チェックをスキップ（確定時間未設定）
  ├─ select_for_update() で対象車輌の割当レコードを行ロック
  └─ 重複あり → ConflictError を raise
```

### Week 4 — 単価・原価管理 + 乖離分析（DashboardQueryService）

| ファイル | 内容 |
|---------|------|
| `src/apps/performances/services/freelance_rate_service.py` | `get_applicable_rate()` を追加（LockService 向け公開 API） |
| `src/apps/performances/services/vehicle_service.py` | `finalize_vehicle_cost(assignment, amount)` を追加 |
| `src/apps/performances/services/dashboard_query_service.py` | **新規** 乖離分析クエリ（人員不足・時間乖離・Lock 漏れ） |
| `src/apps/performances/tests/test_dashboard_query_service.py` | **新規** TC-GAP-01/02 + Lock 漏れ検出テスト（14 ケース） |

#### Week 4 で実装した仕様メモ

```
FreelanceRateService.get_applicable_rate(user, performance, position, target_date)
  └─ get_active_rate() への引数順序ラッパー（設計仕様準拠）

VehicleService.finalize_vehicle_cost(assignment, amount)
  ├─ assignment.is_locked == True → ValidationError
  ├─ amount < 0 → ValidationError
  └─ VehicleAssignment.applied_cost_amount = amount を保存

DashboardQueryService.get_staffing_shortages()
  └─ Count('assignments') アノテーション → actual_count < requested_staff_count でフィルタ

DashboardQueryService.get_schedule_drifts(threshold_minutes=30)
  └─ Q(scheduled_start >= requested_start + Δ) | Q(scheduled_start <= requested_start - Δ)

DashboardQueryService.get_unlocked_past_slots()
  └─ phase__suggested_date < today かつ status != LOCKED
```

---

## svr 固有の設定値

| 項目 | 値 |
|-----|---|
| コンテナ名（web） | `svr_web` |
| 開発ポート | `8085`（rf_finder が 8084 を使用中） |
| DB コンテナ名 | `svr_db` |
| DB 開発ポート | `3310` |
| Docker ネットワーク | `svr_network`（内部）+ `shin-on-internal`（Portal 通信用） |
| GitHub リポジトリ | `https://github.com/satoshi-tateishi/svr` |
| デプロイブランチ | `release` |

---

## Week 5 で実装するもの（次回作業）

### 目標：LockService + スナップショット確定

```
Step 1: LockService（新規）
  ├─ lock_phase_slot(slot): PhaseSlot を Locked に遷移し、スタッフ単価をスナップショット保存
  │    ├─ FreelanceRateService.get_applicable_rate() で単価取得
  │    ├─ applied_unit_price / applied_allowance_total / applied_total_amount を StaffAssignment に保存
  │    └─ PhaseSlot.status = LOCKED、locked_at を設定
  └─ lock_vehicle_operation(operation): VehicleOperation を Locked に遷移し、原価をスナップショット保存
       ├─ VehicleAssignment.applied_cost_amount / applied_sales_amount を保存
       └─ VehicleOperation.status = LOCKED、locked_at を設定

Step 2: AuditLogService（新規）
  └─ TC-LOG-07 の「時間乖離承認ログ」等を記録

Step 3: テスト
  ├─ TC-SNAP-06: 人員・配車同時 Lock → スナップショット確認
  └─ TC-SNAP-07: 外注原価 0 円の警告検知
```

### 参照ドキュメント（Week 5 用）

| ドキュメント | 内容 |
|------------|------|
| `docs/03_SERVICE_LAYER_v4.md` | LockService の設計仕様（4章） |
| `docs/09_TEST_CASE_DESIGN_v3.md` | TC-SNAP-06/07、TC-LOG-07 |

---

## テストの実行方法

### 通常のテスト実行（web コンテナ起動済みの場合）

```bash
docker compose exec web python -m pytest apps/performances/tests/ -v
```

### web コンテナが停止している場合（推奨）

manage.py が存在しないため `docker compose exec` は使えない。
`docker run` で直接 pytest を実行する:

```bash
docker run --rm \
  --network svr_svr_network \
  -e DJANGO_SETTINGS_MODULE=config.settings_test \
  -e SECRET_KEY=test-secret-key-pytest-only \
  -e DEBUG=True \
  -e DATABASE_URL=sqlite://:memory: \
  -v /Users/satoshi/svr/src:/app \
  -v /Users/satoshi/svr/pyproject.toml:/pyproject.toml \
  -w /app \
  svr_web \
  python -m pytest apps/performances/tests/ -v
```

**注意**: `DJANGO_SETTINGS_MODULE` を環境変数で明示しないと、
Dockerfile の `ENV DJANGO_SETTINGS_MODULE=config.settings` が優先されて MySQL に接続しようとする。

### イメージ再ビルドが必要な場合

```bash
cd /Users/satoshi/svr
docker compose build web
```

---

## 初回セットアップ手順（環境が未構築の場合）

### 1. 環境変数を設定

```bash
cd /Users/satoshi/svr
cp .env.sample .env
# .env を編集して SECRET_KEY・DB パスワード等を設定
```

### 2. shin-on-internal ネットワークを確認・作成

```bash
# 作成済みか確認
docker network ls | grep shin-on-internal

# 未作成の場合のみ実行
docker network create shin-on-internal
docker network connect shin-on-internal portal-app
```

### 3. shin-on_portal の PORTAL_ALLOWED_REDIRECT_HOSTS を確認

```bash
grep PORTAL_ALLOWED_REDIRECT_HOSTS /Users/satoshi/shin-on_portal/portal-app/.env
# → ["localhost"] が含まれていれば OK
```

### 4. マイグレーションと起動

```bash
docker compose up -d
# manage.py は src/ に存在しない（runserver は起動しないが DB・Redis は正常起動する）
# マイグレーションは docker run で実行:
docker run --rm \
  --network svr_svr_network \
  --env-file /Users/satoshi/svr/.env \
  -v /Users/satoshi/svr/src:/app \
  -w /app \
  svr_web \
  python -c "import django; django.setup(); from django.core.management import call_command; call_command('migrate')"
```

---

## 動作確認チェックリスト（Week 4 完了後）

```
✅ pytest で全 46 テストが green であること（Week 4 で 14 テスト追加）
✅ FreelanceRateService.get_applicable_rate() が LockService 向けに呼び出せること
✅ VehicleService.finalize_vehicle_cost() が Locked 済み割当で ValidationError を raise すること
✅ DashboardQueryService.get_staffing_shortages() が人員不足スロットを正しく返すこと
✅ DashboardQueryService.get_schedule_drifts() が 30 分以上乖離の工程を検出すること
✅ DashboardQueryService.get_unlocked_past_slots() が Lock 漏れ項目を検出すること
```

## 動作確認チェックリスト（Week 3 完了後）

```
✅ pytest で全 32 テストが green であること
✅ ConflictError が performances.exceptions からインポートできること
✅ AssignmentService.confirm_staff_assignment() が重複時に ConflictError を raise すること
✅ AssignmentService.confirm_vehicle_assignment() が外注車輌を重複判定から除外すること
```

---

## JWT 連携の詳細

### ポータルが発行するクッキー

| クッキー名 | 用途 | 有効期限 |
|-----------|------|---------|
| `otp_verified=true` | Apache ゲートウェイのアクセス制御 | 24時間 |
| `portal_jwt=<JWT>` | svr のユーザー識別 | 24時間 |

### JWT ペイロード

```json
{
  "iss": "https://portal.shin-on1981.com",
  "sub": "<portal_uuid>",
  "aud": "shin-on-apps",
  "email": "user@shin-on1981.com",
  "name": "山田太郎",
  "given_name": "太郎",
  "family_name": "山田",
  "phonetic_given_name": "たろう",
  "phonetic_family_name": "やまだ",
  "phone_number": "09012345678",
  "is_active": true
}
```

**重要**: `sub` は `portal_uuid`（= Portal の `User.username`、UUID v4）。
不変の識別子として `UserProfile.portal_uuid` に保存し、
`StaffAssignment.user` の参照元として使用する。

### ユーザー照合ロジック（PortalJWTMiddleware）

```
portal_jwt 受信
  ├─[1] portal_uuid で UserProfile 検索 → 見つかれば即返す + phone_number を常時同期
  ├─[2] email で User 検索 → 見つかれば portal_uuid を紐付け
  └─[3] 見つからない → JWT ペイロードで新規ユーザーを自動作成
```

**注意**: 新規作成時は `user.profile` 経由でアクセスすること（`get_or_create` 使用不可）。
`login()` 発火の post_save シグナルで `portal_uuid=None` に上書きされるバグを回避するため。

---

## 重要なハマりポイント

### post_save シグナルとの干渉バグ（Week 1 で解決済み）

```python
# ❌ 間違い: get_or_create だと portal_uuid が None に上書きされる
profile, _ = UserProfile.objects.get_or_create(user=user)

# ✅ 正しい: user.profile 経由でキャッシュを更新する
profile = user.profile
profile.portal_uuid = portal_uuid
profile.save()
```

詳細: `/Users/satoshi/rf_finder/docs/01_APP_INTEGRATION_GUIDE.md` 参照。

### Ruff はリポジトリルートから実行する

```bash
# ✅ 正しい（pyproject.toml が読まれる）
ruff check src/ --fix && ruff format src/

# ❌ 間違い（Docker コンテナ内では pyproject.toml が見つからない）
docker compose exec web ruff check .
```

### テストは DJANGO_SETTINGS_MODULE を明示して実行する

Dockerfile に `ENV DJANGO_SETTINGS_MODULE=config.settings` が設定されているため、
テスト実行時は環境変数で明示的に上書きしないと MySQL 接続を試みてしまう。

```bash
# ✅ 正しい（-e で settings_test を指定）
docker run --rm ... -e DJANGO_SETTINGS_MODULE=config.settings_test ... svr_web python -m pytest ...

# ❌ 間違い（Dockerfile の ENV が優先されて MySQL に接続しようとする）
docker run --rm ... svr_web python -m pytest ...
```

### manage.py が存在しない（Week 3 時点の既知事項）

`src/` に `manage.py` が未作成のため `docker compose exec web python manage.py` は使えない。
テスト・マイグレーション等は `docker run` コマンドで直接実行する（テストの実行方法セクション参照）。

---

## 参照ドキュメント

| ドキュメント | 場所 |
|------------|------|
| 要件定義 | `docs/01_REQUIREMENTS_v7.md` |
| ER図 | `docs/02_ERD_v3.md` |
| サービス層設計 | `docs/03_SERVICE_LAYER_v4.md` |
| 権限設計 | `docs/05_PERMISSION_DESIGN_v3.md` |
| 監査ログ設計 | `docs/06_AUDIT_LOG_DESIGN_v3.md` |
| Django 実装テンプレート | `docs/07_DJANGO_IMPLEMENTATION_TEMPLATE_v3.md` |
| Docker 本番テンプレート | `docs/08_DOCKER_PRODUCTION_TEMPLATE_v3.md` |
| テストケース設計 | `docs/09_TEST_CASE_DESIGN_v3.md` |
| 8週間ロードマップ | `docs/10_IMPLEMENTATION_ROADMAP_8WEEKS_v4.md` |
| JWT 連携正典（rf_finder） | `/Users/satoshi/rf_finder/docs/01_APP_INTEGRATION_GUIDE.md` |
