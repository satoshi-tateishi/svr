# プロジェクト: svr (演劇制作人員・配車・工程管理システム)

## 0. 基本方針
- **動作環境**: 本アプリケーションは Docker 環境で動作します。開発・テスト・実行は Docker コンテナ内で行うことを前提とします。
- **言語**: ユーザーへの回答、解説、ドキュメント、コード内コメントは、常に**日本語**で行うこと。
- **コード品質**: 全ての Python コードはコミット前に Ruff チェック（`ruff check`）およびフォーマット（`ruff format`）を通過しなければなりません。
- **AI実装の厳守事項**:
    - ビジネスロジックは必ずサービス層（`src/apps/performances/services/`）に実装し、ビューに直接書かないこと。
    - **Lock の不可逆性**: `LockService` で確定したデータは絶対に解除・変更しない。修正が必要な場合は「調整用レコード」を新規作成する。
    - **トランザクション管理**: Lock 処理などは `@transaction.atomic` と `select_for_update()` を必須で使用すること。
    - **スナップショット優先**: SaaS 連携、帳票出力、集計には必ず `applied_` で始まるスナップショット項目のみを使用すること。

## 1. プロジェクト概要
演劇制作におけるスタッフ配置、車輌配車、および標準工程（1〜9工程）を一元管理する Django ベースのシステム。
ダブルブッキング防止、Lock による実績確定（スナップショット保存）、および PDF 帳票出力を提供する。
**shin•on Portal** と JWT 連携（SSO）を行い、認証を統合している。

## 2. 技術スタック
- **Backend**: Django (Python 3.12)
- **Frontend**: Tailwind CSS (インライン CSS は厳禁)
- **Database**: MySQL 8.4 LTS
- **Cache/Session**: Redis
- **Auth**: PortalJWTMiddleware (shin•on Portal JWT 連携)
- **PDF**: WeasyPrint
- **Infrastructure**: Docker / Apache (Reverse Proxy)

## 3. 重要な業務ロジック・工程定義

### 3.1 演劇標準 9 工程 (TEMPLATE_STEPS)
`PhaseService` により以下の工程がテンプレート展開される：
1. 機材作り
2. 稽古場仕込み
3. 稽古
4. 稽古場バラシ
5. 劇場仕込み
6. 舞台稽古
7. 本番
8. 劇場バラシ
9. ツアー・最終荷降ろし

### 3.2 Lock 設計（最重要）
- **不可逆性**: 一度 `LOCKED` ステータスになった `PhaseSlot` や `VehicleOperation` は変更不可。
- **スナップショット**: Lock 時に `StaffAssignment` や `VehicleAssignment` にその時点の単価・原価を `applied_*` フィールドへ保存する。
- **単価履歴**: `FreelanceRateService` により期間重複を許さない単価履歴管理を行う。

## 4. 主要機能要件
1. **工程テンプレート展開**: 公演に対して標準 9 工程を冪等性を保ちつつ一括生成。
2. **人員・車輌割当**: ダブルブッキング防止ロジックを備えたアサイン管理。
3. **実績確定 (Lock)**: トランザクションを保護した状態での金額・時間スナップショットの確定。
4. **PDF 帳票出力**:
    - **公演手配書**: 現場配布用（金額非表示）。
    - **手配実績証明書**: 経理提出用（Lock 済みデータから `applied_` フィールドを参照）。
5. **ポータル連携**: JWT (`portal_jwt`) による SSO とユーザー自動紐付け・作成。

## 5. 開発・運用コマンド

### 5.1 テストの実行 (Docker 必須)
```bash
docker run --rm 
  -e DJANGO_SETTINGS_MODULE=config.settings_test 
  -e SECRET_KEY=test-secret-key-pytest-only 
  -v $(pwd)/src:/app 
  -v $(pwd)/pyproject.toml:/pyproject.toml 
  -w /app 
  svr_web 
  python -m pytest apps/performances/tests/
```

### 5.2 コード品質 (Ruff)
※必ずホスト（リポジトリルート）から実行すること。
```bash
ruff check src/ --fix && ruff format src/
```

## 6. ドキュメント
- **設計ドキュメント**: `/Users/satoshi/svr/docs/`
    - `01_REQUIREMENTS_v7.md`: 要件定義・設計原則
    - `02_ERD_v3.md`: データベース設計
    - `03_SERVICE_LAYER_v4.md`: サービス層詳細
    - `07_DJANGO_IMPLEMENTATION_TEMPLATE_v3.md`: 実装テンプレート
- **CLAUDE.md**: 開発ガイドライン（Claude Code 用）

## 7. ディレクトリ構造
- `src/apps/accounts/`: 認証・ポータル連携
- `src/apps/performances/`: 公演・人員・配車（コアドメイン）
    - `models/`: 分割されたモデル定義
    - `services/`: **ビジネスロジックの唯一の置き場所**
    - `tests/`: ユニットテスト
- `src/templates/`: Django テンプレート (Tailwind CSS 使用)
- `docs/`: 最新の設計・仕様書
