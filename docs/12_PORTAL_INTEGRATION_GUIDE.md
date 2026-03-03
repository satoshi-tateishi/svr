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
| Week 3 | ダブルブッキング防止（AssignmentService） | 🔜 次回 |
| Week 4 | 単価・原価管理 + 乖離分析 | 未着手 |
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

## Week 3 で実装するもの（次回作業）

### 目標：ダブルブッキングを物理的に遮断する

```
Step 1: AssignmentService.confirm_staff_assignment()
  ├─ 対象スタッフの全 StaffAssignment を取得
  ├─ 占有時間（occupied_start〜occupied_end）が重複するものを検索
  └─ 重複があれば ConflictError を raise（DB には保存しない）

Step 2: AssignmentService.confirm_vehicle_assignment()
  ├─ 対象車輌の全 VehicleAssignment を取得
  ├─ scheduled_start〜scheduled_end が重複するものを検索
  ├─ 外注車輌（Vehicle.ownership_type == 'external'）は重複判定から除外
  └─ 重複があれば ConflictError を raise

Step 3: select_for_update() によるトランザクション制御
  └─ 並行アクセス時の競合を防ぐため、DB ロックを取得してから判定
```

### 新規作成ファイル

| ファイル | 内容 |
|---------|------|
| `src/apps/performances/services/assignment_service.py` | **最重要** 重複チェック付き人員・車輌割当 |
| `src/apps/performances/exceptions.py` | `ConflictError`（ダブルブッキング用カスタム例外） |
| `src/apps/performances/tests/test_assignment_service.py` | 重複チェックのテスト |

### 参照ドキュメント

| ドキュメント | 内容 |
|------------|------|
| `docs/01_REQUIREMENTS_v7.md` | ダブルブッキング防止の要件定義 |
| `docs/03_SERVICE_LAYER_v4.md` | AssignmentService の設計仕様 |
| `docs/09_TEST_CASE_DESIGN_v3.md` | TC-VH-03（車輌重複拒否）等のテストケース |

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

### 4. Django プロジェクトのスキャフォールド（未実施の場合）

```bash
# manage.py と wsgi.py が存在しない場合のみ実行
docker compose run --rm web django-admin startproject config_tmp .
# ※ config/ は既に存在するため startproject は使わず手動で manage.py / wsgi.py を作成
```

### 5. マイグレーションと起動

```bash
docker compose up -d
docker compose exec web python manage.py makemigrations accounts performances
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

---

## 動作確認チェックリスト（Week 1 + 2 完了後）

```
□ http://localhost:8085/ にアクセス → ポータルログインへリダイレクト
□ SSO + OTP 認証完了 → /performances/ に戻り一覧が表示される
□ /performances/create/ で公演を作成できる
□ 詳細画面の「9工程を一括展開」ボタンを押すと 1〜9 工程が生成される
□ 2回目の展開ボタンでエラーメッセージが表示される（冪等性ガード）
□ /admin/accounts/userprofile/ に UserProfile が自動作成されている
□ /admin/performances/vehicle/ で車輌マスタを登録できる
□ pytest で全テストが green であること
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

### テストは Docker コンテナ内で実行する

```bash
docker compose exec web python -m pytest apps/performances/tests/ -v
```

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
