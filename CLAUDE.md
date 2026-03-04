# CLAUDE.md

このファイルは Claude Code（claude.ai/code）がこのリポジトリのコードを扱う際のガイドを提供します。

## 重要なプロジェクトガイドライン

**IMPORTANT**: このプロジェクトには厳守すべき要件があります。

1. **言語要件**: **必ず日本語で対応してください。** 全ての会話、説明、ドキュメント、コメントは日本語で記載してください。このプロジェクトは日本語環境で運用されています。

2. **ドキュメント参照**: 最新の設計・要件は `/Users/satoshi/svr/docs` に保管されています。機能を実装する前に**必ず**これらを参照してください。

3. **コード品質**: 全ての Python コードはコミット前に Ruff チェック（`ruff check`）およびフォーマット（`ruff format`）を通過しなければなりません。

4. **Tailwind CSS のみ使用**: インライン CSS（style 属性）は**厳禁**です。Tailwind CSS クラスのみを使用してください。

5. **サービス層パターン**: ビジネスロジックはサービス層（`src/apps/performances/services/`）に実装しなければなりません。ビューに直接ロジックを書かないでください。

6. **Lock の不可逆性**: `LockService` で確定した Slot / Operation は絶対に解除しない。修正が必要な場合は「調整用レコード」を新規作成する。

---

## プロジェクト概要

**svr**（演劇制作人員・配車・工程管理システム）は Django ベースの公演手配管理システムです。演劇制作の標準工程（1〜9 工程）のテンプレート展開、スタッフ・車輌のダブルブッキング防止、Lock によるスナップショット確定、PDF 帳票出力を提供します。

**shin•on Portal**（`portal.shin-on1981.com`）と JWT 連携し、ポータルが発行した `portal_jwt` クッキーを検証してシングルサインオンを実現します。

### 主要アーキテクチャ

- **Apache リバースプロキシ**: `otp_verified` クッキーによる認証ガード + `portal_jwt` の転送
- **PortalJWTMiddleware**: `portal_jwt` を検証し Django セッションに紐付ける
- **サービス層**: ビジネスロジックを Views から完全分離
- **Lock 後不変性**: Lock 済みの Slot / Operation の変更は一切禁止

---

## 開発コマンド

### Docker 環境

```bash
# コンテナ起動
docker compose up -d

# ログ確認
docker compose logs -f web
```

### テストの実行

**テストは必ず Docker コンテナ内で実行すること。**

```bash
# 全テスト実行（推奨）
docker run --rm \
  -e DJANGO_SETTINGS_MODULE=config.settings_test \
  -e SECRET_KEY=test-secret-key-pytest-only \
  -e DEBUG=True \
  -e DATABASE_URL=sqlite://:memory: \
  -v /Users/satoshi/svr/src:/app \
  -v /Users/satoshi/svr/pyproject.toml:/pyproject.toml \
  -w /app \
  svr_web \
  python -m pytest apps/performances/tests/ -v --no-header -p no:logging

# 特定ファイルのみ
docker run --rm \
  -e DJANGO_SETTINGS_MODULE=config.settings_test \
  -e SECRET_KEY=test-secret-key-pytest-only \
  -e DEBUG=True \
  -e DATABASE_URL=sqlite://:memory: \
  -v /Users/satoshi/svr/src:/app \
  -v /Users/satoshi/svr/pyproject.toml:/pyproject.toml \
  -w /app \
  svr_web \
  python -m pytest apps/performances/tests/test_report_service.py -v
```

### コード品質（Ruff）

**MANDATORY**: 全ての作成・変更した Python コードはコミット前に Ruff チェックを通過すること。

**重要**: Ruff は必ずリポジトリルート（`pyproject.toml` がある場所）から実行すること。
Docker コンテナ内から実行すると `pyproject.toml` が読み込まれず、クォートスタイルやマイグレーション除外設定が効かなくなる。

```bash
# チェック＆自動修正
ruff check src/ --fix

# フォーマット
ruff format src/

# 両方（コミット前に必須）
ruff check src/ --fix && ruff format src/
```

### イメージ再ビルド

```bash
cd /Users/satoshi/svr
docker compose build web
```

### マイグレーション

```bash
docker run --rm \
  --network svr_svr_network \
  --env-file /Users/satoshi/svr/.env \
  -v /Users/satoshi/svr/src:/app \
  -w /app \
  svr_web \
  python -c "import django; django.setup(); from django.core.management import call_command; call_command('migrate')"
```

---

## アーキテクチャ

### サービス層パターン

ビジネスロジックはサービス層に集約する。全サービスは `src/apps/performances/services/` に配置。

| サービス | 責務 |
|---------|------|
| `phase_service.py` | **最重要** 演劇標準 9 工程の一括展開（冪等性ガード付き） |
| `performance_service.py` | 公演 CRUD |
| `assignment_service.py` | **最重要** ダブルブッキング防止付き人員・車輌割当 |
| `vehicle_service.py` | 車輌マスタ・運行工程の確定原価入力 |
| `freelance_rate_service.py` | 単価履歴管理（期間重複禁止） |
| `dashboard_query_service.py` | 乖離分析（人員不足・時間乖離・Lock 漏れ） |
| `lock_service.py` | **最重要** スナップショット確定（`@transaction.atomic`） |
| `report_service.py` | Lock 済みスナップショットから PDF 帳票を生成 |

**Critical**: ビジネスロジックは常にサービス層を使用すること。ビューに認証・判定ロジックを直接書かない。

### 認証フロー（PortalJWTMiddleware）

```
portal_jwt クッキー受信
  ├─[1] portal_uuid（JWT sub）で UserProfile 検索 → 見つかれば即返す
  ├─[2] email で User 検索 → 見つかれば portal_uuid を自動リンク
  └─[3] 見つからない → JWT ペイロードで新規ユーザーを自動作成
```

**注意**: 新規作成時は `user.profile` 経由でアクセスすること（`get_or_create` 使用不可）。
`login()` 発火の post_save シグナルで `portal_uuid=None` に上書きされるバグを回避するため。

### Lock 設計（最重要）

```
LockService.lock_phase_slot(slot)
  ├─ @transaction.atomic + select_for_update() で PhaseSlot を行ロック
  ├─ 各 StaffAssignment に FreelanceRateService で単価取得
  │    └─ applied_unit_price / applied_allowance_total / applied_total_amount を保存
  └─ PhaseSlot.status = LOCKED

LockService.lock_vehicle_operation(operation, force=False)
  ├─ @transaction.atomic + select_for_update() で VehicleOperation を行ロック
  ├─ force=False: 外注車輌の applied_cost_amount が 0 → ZeroCostWarning を raise
  └─ VehicleOperation.status = LOCKED
```

**Lock 後は絶対に変更不可**。解除 API は存在しない。修正は「調整用レコードを新規作成」する。

### PDF 帳票出力（ReportService）

```
ReportService.generate_performance_report(performance) -> bytes
  └─ 公演手配書（現場スタッフ・ドライバー配布用）。金額非表示。

ReportService.generate_financial_report(performance) -> bytes
  └─ 手配実績証明書（経理提出用）。applied_* フィールドのみ参照。

共通制約:
  ├─ Lock 済みデータ（status == LOCKED）からのみ生成可能
  └─ Lock 済みデータが存在しない場合は ValidationError を raise
```

**SaaS 連携原則**: 外部参照は必ず `applied_` で始まるスナップショット項目のみを使用する。

### データモデル

**UserProfile** (`apps/accounts/models.py`):
- Django 標準 User モデルを OneToOne で拡張
- `portal_uuid`: shin•on Portal の不変 ID（JWT `sub`）。外部参照・データ交換に使用する
- `system_role`: システム全体のロール（ADMIN / EDITOR / GENERAL / VIEWER）

**Performance / Phase / PhaseSlot** (`apps/performances/models/base.py`):
- `PhaseSlot.status`: DRAFT → ASSIGNED → LOCKED（Lock 後は不可逆）

**StaffAssignment** (`apps/performances/models/staff.py`):
- `applied_*` フィールド: Lock 時に確定するスナップショット（Lock 前は null）

**VehicleAssignment** (`apps/performances/models/vehicle.py`):
- `applied_cost_amount`: Lock 時に確定する原価スナップショット

---

## 設定

環境変数は `.env` ファイルで管理（`.env.sample` がテンプレート）。

### 重要な環境変数

| 変数 | 用途 |
|-----|------|
| `SECRET_KEY` | Django シークレットキー |
| `DATABASE_URL` | MySQL 接続文字列（`mysql://user:pass@host:port/dbname`） |
| `REDIS_URL` | Redis 接続 URL（セッション・Celery 用） |
| `PORTAL_JWKS_URL` | Portal の JWKS エンドポイント（`http://portal-app:8000/api/jwks/`） |
| `PORTAL_JWT_ISSUER` | JWT の iss クレーム照合用（`https://portal.shin-on1981.com`） |
| `PORTAL_JWT_AUDIENCE` | JWT の aud クレーム照合用（`shin-on-apps`） |
| `PORTAL_LOGIN_URL` | 未認証時のリダイレクト先 |
| `DEBUG` | `True`（開発）/ `False`（本番） |

---

## デプロイ構成

Docker Compose によるマルチコンテナ構成:

| コンテナ名 | 役割 | ポート |
|-----------|------|-------|
| `svr_web` | Django（Gunicorn / runserver） | `8085`（ホスト） |
| `svr_db` | MySQL 8.4 LTS | `3310`（ホスト） |
| Redis | セッション・Celery ブローカー | 内部のみ |

**ネットワーク**:
- `svr_network`: コンテナ間通信（内部）
- `shin-on-internal`: Portal との通信用（外部共有ネットワーク）

**注意**: `manage.py` は `src/` に存在しないため、`docker compose exec web python manage.py` は使えない。テスト・マイグレーションは `docker run` で直接実行すること（テストの実行方法セクション参照）。

---

## コードスタイルガイドライン

**必須要件**:
- 全コードは Ruff チェック・フォーマットを通過すること（`pyproject.toml` 設定）
- 行長: 100 文字
- 文字列: シングルクォート
- インポート順: 標準ライブラリ → サードパーティ → ローカル

**日本語使用規則**:
- `verbose_name`、`verbose_name_plural` は必ず日本語で記載
- コメント（`# コメント`）は日本語で記載
- ユーザー向けメッセージ（エラーメッセージ、通知等）は日本語で記載
- docstring も日本語で記載

**Ruff 設定**（`pyproject.toml`）:
- ターゲット: Python 3.12
- ルール: E / W / F / I（isort）/ B（bugbear）/ C4（comprehensions）/ UP（pyupgrade）
- 除外: `.git`, `.venv`, `__pycache__`, `src/apps/*/migrations/*`

---

## テスト

### テスト基盤の構成

| ファイル | 役割 |
|---------|------|
| `pyproject.toml` | `DJANGO_SETTINGS_MODULE = config.settings_test` を指定 |
| `src/config/settings_test.py` | テスト用設定（インメモリ SQLite・LocMemCache） |
| `src/apps/performances/tests/` | テストファイル群 |

### 重要: DJANGO_SETTINGS_MODULE を明示する

Dockerfile に `ENV DJANGO_SETTINGS_MODULE=config.settings` が設定されているため、
テスト実行時は `-e DJANGO_SETTINGS_MODULE=config.settings_test` を明示的に指定すること。

```bash
# ✅ 正しい
docker run --rm -e DJANGO_SETTINGS_MODULE=config.settings_test ... svr_web python -m pytest ...

# ❌ 間違い（Dockerfile の ENV が優先されて MySQL に接続しようとする）
docker run --rm ... svr_web python -m pytest ...
```

### テストファイル一覧

| ファイル | テスト数 | 内容 |
|---------|---------|------|
| `test_models.py` | — | モデルテスト |
| `test_phase_service.py` | 9 | テンプレート展開の全ケース |
| `test_assignment_service.py` | 12 | ダブルブッキング防止 |
| `test_dashboard_query_service.py` | 14 | 乖離分析クエリ |
| `test_lock_service.py` | 15 | スナップショット確定 |
| `test_report_service.py` | 21 | PDF 帳票生成 |

---

## ディレクトリ構成

```
svr/
├── src/
│   ├── apps/
│   │   ├── accounts/              # 認証・ユーザー管理
│   │   │   ├── middleware.py      # PortalJWTMiddleware
│   │   │   ├── models.py          # UserProfile（portal_uuid・システムロール）
│   │   │   ├── views.py           # login_view / logout_view
│   │   │   └── admin.py           # Admin UI
│   │   └── performances/          # 公演手配管理（コアドメイン）
│   │       ├── models/
│   │       │   ├── base.py        # Performance / Phase / PhaseSlot / PerformancePosition
│   │       │   ├── staff.py       # StaffAssignment / PerformanceFreelanceRate
│   │       │   └── vehicle.py     # Vehicle / VehicleOperation / VehicleAssignment
│   │       ├── services/          # ← ビジネスロジックの唯一の置き場所
│   │       │   ├── phase_service.py
│   │       │   ├── assignment_service.py
│   │       │   ├── lock_service.py
│   │       │   ├── report_service.py
│   │       │   ├── dashboard_query_service.py
│   │       │   ├── freelance_rate_service.py
│   │       │   ├── vehicle_service.py
│   │       │   └── performance_service.py
│   │       ├── tests/             # ユニットテスト
│   │       ├── exceptions.py      # ConflictError / ZeroCostWarning
│   │       ├── views.py           # ビュー（ロジックなし、サービス層委譲のみ）
│   │       ├── urls.py
│   │       └── admin.py
│   ├── config/
│   │   ├── settings.py            # 本番・開発設定
│   │   ├── settings_test.py       # テスト専用設定（インメモリ SQLite）
│   │   └── urls.py
│   └── templates/
│       ├── base.html
│       └── performances/
│           ├── list.html
│           ├── create.html
│           ├── detail.html
│           └── reports/
│               ├── performance_report.html  # 公演手配書テンプレート
│               └── financial_report.html    # 手配実績証明書テンプレート
├── docs/                          # 設計ドキュメント（実装前に必ず参照）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── pyproject.toml                 # Ruff・pytest 設定
```

**Critical ディレクトリ**:
- `src/apps/performances/services/`: ビジネスロジック層（唯一の置き場所）
- `src/apps/performances/tests/`: ユニットテスト
- `src/templates/performances/reports/`: PDF 帳票 HTML テンプレート
- `docs/`: 設計仕様（実装前に**必ず**参照すること）

---

## よくあるハマりポイント

- **言語**: このプロジェクトは日本語環境です。全ての対応・コメント・メッセージは日本語で記載すること
- **ドキュメント優先**: 機能実装前に `/Users/satoshi/svr/docs` の設計仕様を必ず確認すること
- **manage.py が存在しない**: `src/` に `manage.py` がないため `docker compose exec web python manage.py` は使えない。`docker run` で実行すること
- **Ruff 実行場所**: `ruff` はリポジトリルートから実行すること（Docker コンテナ内は不可）
- **テスト環境変数**: `DJANGO_SETTINGS_MODULE=config.settings_test` を明示しないと MySQL に接続しようとする
- **Lock の不可逆性**: Lock 済み Slot / Operation を変更するコードを書かない。修正は「調整用レコードの新規作成」で対応する
- **applied_* フィールド**: SaaS 連携・PDF 生成・集計には必ず `applied_` で始まるスナップショット項目のみを使用する
- **portal_uuid**: 外部参照・JWT `sub` には `UserProfile.portal_uuid` を使用する（`user.id` は使わない）
- **ユーザー作成禁止**: ユーザーは `PortalJWTMiddleware` が自動作成する。手動で `User.objects.create_*` を呼ぶな
- **post_save シグナルバグ**: 新規ユーザー作成後は `user.profile`（キャッシュ経由）でアクセスすること。`get_or_create` は使わない
- **CSS ルール**: インライン CSS（style 属性）は厳禁。Tailwind CSS クラスのみ使用すること
- **サービス層**: ビジネスロジックは `services/` に実装する。`views.py` に判定・計算ロジックを書かない
