# AI.md

このファイルは Codex がこのリポジトリのコードを扱う際のガイドを提供します。

## 重要なプロジェクトガイドライン

**IMPORTANT**: このプロジェクトには厳守すべき要件があります。

1. **言語要件**: **必ず日本語で対応してください。** 全ての会話、説明、ドキュメント、コメントは日本語で記載してください。
2. **ドキュメント参照**: 最新の設計・要件は `/Users/satoshi/svr/docs` に保管されています。機能実装前に必ず参照してください。
3. **コード品質**: 全ての Python コードはコミット前に `ruff check` と `ruff format` を通過させてください。
4. **Tailwind CSS のみ使用**: インライン CSS（`style` 属性）は禁止です。Tailwind CSS クラスのみ使用してください。
5. **サービス層優先**: ビジネスロジックは原則としてサービス層へ置いてください。特に `src/apps/performances/services/` の責務を崩さないこと。
6. **Lock の不可逆性**: `LockService` で確定した Slot / Operation は解除しません。修正は調整用レコード追加で吸収する前提です。

## プロジェクト概要

`svr` は Django ベースの演劇制作向け管理システムです。現在の実装は次の 2 ドメインに分かれています。

- `productions`: 公演、工程ブロック、申請入力、車両手配管理
- `performances`: 実績公演、標準工程、割当、Lock、PDF、乖離ダッシュボード

`shin•on Portal` と JWT 連携し、Portal が発行した `portal_jwt` クッキーを `PortalJWTMiddleware` で検証してシングルサインオンを実現します。

## 現在の重要な実装事実

### ドメイン境界

- `Production` と `Performance` は別モデルです
- `productions` と `performances` の自動同期層は未実装です
- 申請系 UI は `productions` が中心です

### 権限

- 全体権限: `UserProfile.system_role`
- 公演単位権限: `ProductionMember.role`
- 権限判定は `src/apps/productions/services/permissions.py` に集約されています

### Lock

- `LockService.lock_phase_slot()` が `StaffAssignment.applied_*` を確定します
- `LockService.lock_vehicle_operation()` が `VehicleAssignment.applied_cost_amount` を確定します
- 解除 API は存在しません

### テンプレート展開

- `PhaseService` の標準工程は **10 工程** です
- 旧資料の「9 工程」記述を前提に実装しないでください

## 開発コマンド

### Docker 環境

```bash
docker compose up -d
docker compose logs -f web
```

### テストの実行

**テストは Docker コンテナ内で実行すること。**

```bash
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
```

```bash
docker run --rm \
  -e DJANGO_SETTINGS_MODULE=config.settings_test \
  -e SECRET_KEY=test-secret-key-pytest-only \
  -e DEBUG=True \
  -e DATABASE_URL=sqlite://:memory: \
  -v /Users/satoshi/svr/src:/app \
  -v /Users/satoshi/svr/pyproject.toml:/pyproject.toml \
  -w /app \
  svr_web \
  python -m pytest apps/productions/tests/ -v --no-header -p no:logging
```

### コード品質

**重要**: Ruff は必ずリポジトリルートから実行してください。

```bash
ruff check src/ --fix
ruff format src/
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
  python manage.py migrate
```

## アーキテクチャ

### `performances` サービス層

| サービス | 責務 |
|---------|------|
| `phase_service.py` | 標準 10 工程の一括展開 |
| `performance_service.py` | 実績公演 CRUD |
| `assignment_service.py` | ダブルブッキング防止付き人員・車輌割当 |
| `vehicle_service.py` | 車輌マスタ・原価入力 |
| `freelance_rate_service.py` | 単価履歴管理 |
| `dashboard_query_service.py` | 人員不足・時間乖離・Lock 漏れの抽出 |
| `lock_service.py` | スナップショット確定 |
| `report_service.py` | Lock 済みデータから PDF 生成 |

### `productions` の現状

- View 主導の実装がまだ多いです
- ただし権限判定は `services/permissions.py` と Mixin に寄せています
- HTMX モーダルは成功時に `HX-Redirect` を返す前提です

### 認証フロー

```text
portal_jwt クッキー受信
  ├─ portal_uuid（JWT sub）で UserProfile 検索
  ├─ 見つからなければ email で User を検索して portal_uuid をリンク
  └─ 見つからなければ JWT ペイロードで新規ユーザーを自動作成
```

**注意**: 新規作成直後のプロフィール操作は `user.profile` を使ってください。

## データモデル

### accounts

- `UserProfile`
  - `portal_uuid`
  - `system_role`
  - 氏名、ふりがな、電話番号、email

### productions

- `Production`
- `Process`
- `ProcessDay`
- `ProcessRequestUnit`
- `StaffRequest`
- `VehicleRequest`
- `VehicleAssignment`
- `ProductionMember`

### performances

- `Performance`
- `Phase`
- `PhaseSlot`
- `StaffAssignment`
- `PerformanceFreelanceRate`
- `Vehicle`
- `VehicleOperation`
- `VehicleAssignment`

## 設定

環境変数は `.env` で管理します。

| 変数 | 用途 |
|-----|------|
| `SECRET_KEY` | Django シークレットキー |
| `DATABASE_URL` | MySQL 接続文字列 |
| `REDIS_URL` | Redis 接続 URL |
| `PORTAL_JWKS_URL` | Portal の JWKS エンドポイント |
| `PORTAL_JWT_ISSUER` | JWT の `iss` 照合用 |
| `PORTAL_JWT_AUDIENCE` | JWT の `aud` 照合用 |
| `PORTAL_LOGIN_URL` | 未認証時のリダイレクト先 |
| `DEBUG` | 開発 / 本番切り替え |

## デプロイ構成

Docker Compose によるマルチコンテナ構成:

| コンテナ名 | 役割 | ポート |
|-----------|------|-------|
| `svr_web` | Django 開発サーバ | `8085` |
| `svr_db` | MySQL 8.4 LTS | `3310` |
| `svr_redis` | Redis | 内部のみ |

補足:

- `shin-on-internal` ネットワークを Portal 通信用に使用します
- 現在の Compose は Gunicorn ではなく `runserver` 起動です

## コードスタイル

- 行長: 100 文字
- 文字列: シングルクォート
- インポート順: 標準ライブラリ → サードパーティ → ローカル
- `verbose_name`、コメント、docstring、ユーザー向けメッセージは日本語

## テスト

### テスト基盤

- `pyproject.toml`: `DJANGO_SETTINGS_MODULE = config.settings_test`
- `src/config/settings_test.py`: SQLite in-memory, LocMemCache

### 重要事項

- テスト時は `DJANGO_SETTINGS_MODULE=config.settings_test` を明示すること
- 省略すると Dockerfile / 環境設定により MySQL に接続しようとすることがあります

## ディレクトリ構成

```text
svr/
├── src/
│   ├── apps/
│   │   ├── accounts/
│   │   ├── performances/
│   │   └── productions/
│   ├── config/
│   ├── manage.py
│   └── templates/
├── docs/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── pyproject.toml
```

## よくあるハマりポイント

- 全て日本語で記載する
- 実装前に `/Users/satoshi/svr/docs` を確認する
- `manage.py` は `src/manage.py` にある
- Ruff はリポジトリルートから実行する
- テスト時は `DJANGO_SETTINGS_MODULE=config.settings_test` を明示する
- Lock 済みデータを変更しない
- PDF・集計・外部参照は `applied_*` を基準にする
- 新規ユーザー作成後は `user.profile` を使い、JWT 連携文脈で安易に `get_or_create` しない
- インライン CSS は使わない
- `productions` の権限判定を View に直書きしない
- AuditLog、SaaS 連携、`productions` と `performances` の自動同期は未実装として扱う
