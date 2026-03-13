# プロジェクト概要

`svr` は Django / Docker ベースの演劇制作向け管理システムです。現在の実装は、申請入力を担う `productions` と、確定実績・帳票・Lock を担う `performances` を分離した構成です。

主目的:

- 人員申請の整理
- 車両申請と手配の整理
- 工程ブロック単位の進行管理
- Lock 後スナップショットを使った帳票出力

## 技術スタック

- Django
- MySQL 8.4
- Redis
- Docker Compose
- HTMX
- Alpine.js
- Tailwind CSS
- WeasyPrint

## Django App の責務

### accounts

- `UserProfile` による追加プロフィール管理
- `portal_jwt` クッキーを使った Portal SSO
- `system_role` による全体権限制御

### productions

現行 UI の中心ドメインです。

- `Production` の作成・一覧・詳細
- 工程ブロック (`Process`) と工程日 (`ProcessDay`) の管理
- 申請単位 (`ProcessRequestUnit`) ベースの構成管理
- 人員申請 (`StaffRequest`) と車両申請 (`VehicleRequest`)
- 管理側車両手配 (`productions.VehicleAssignment`)
- 公演単位担当者 (`ProductionMember`)
- 公演単位権限判定

### performances

確定実績・原価・帳票のドメインです。

- 実績公演 (`Performance`)
- 標準工程 (`Phase`, `PhaseSlot`)
- 人員割当 (`StaffAssignment`)
- 単価履歴 (`PerformanceFreelanceRate`)
- 車輌マスタ・運行工程 (`Vehicle`, `VehicleOperation`)
- Lock / PDF / 乖離ダッシュボード

## 現在の設計上の重要点

### 1. `Production` と `Performance` は別集約

- `productions` は申請 UI と工程構成を扱う
- `performances` は確定実績と帳票を扱う
- 現時点では両者を自動同期する統合層は未実装

### 2. Request / Assignment / Operation は部分的に分離済み

- `productions.StaffRequest` / `productions.VehicleRequest` が申請
- `productions.VehicleAssignment` が管理側手配
- `performances.StaffAssignment` / `performances.VehicleOperation` / `performances.VehicleAssignment` が確定実績系

### 3. Lock 後は解除しない

- `LockService` は `PhaseSlot` と `VehicleOperation` を `LOCKED` に遷移させる
- 解除 API は存在しない
- 修正は調整用レコードの新規作成で吸収する前提

### 4. 権限は二層

- 全体権限: `UserProfile.system_role`
- 公演担当権限: `ProductionMember.role`

### 5. HTMX モーダル前提の UI

- `productions` の編集 UI はモーダル主体
- 成功時は `HX-Redirect`
- 権限エラー時は HTMX なら HTML 403、通常リクエストなら通常 403

## URL 構成

- `/auth/`
- `/performances/`
- `/productions/`
- `/` は `/performances/` にリダイレクト

## 現在の実装状況

実装済み:

- Portal JWT 連携
- `productions` の公演詳細・工程構成・人員申請・車両申請・車両手配 UI
- `performances` のテンプレート展開・ダブルブッキング防止・Lock・PDF 出力・ダッシュボード

未実装または限定実装:

- 監査ログ基盤
- 外部 SaaS 連携
- `productions` と `performances` の自動連携
- Celery を使った非同期処理
