# productions テンプレート リファクタリング計画

> 作成日: 2026-03-13
> 対象: `src/templates/productions/` および `src/apps/productions/`
> 更新日: 2026-03-14

---

## 背景・目的

直近のコミット（5586e4c・a6f5e0f）で旧 ProcessDay ベースの画面が `unused/` に退避された。
その結果、以下の問題が残存している：

- モーダルテンプレートの命名規則が揺れている（`_modal` サフィックスの有無が混在）
- `unused/` ディレクトリが削除されずに残っている
- `vehicle_assignment` 関連ビューが URL に未登録の可能性がある

本ドキュメントでは、機能に合わせた名称最適化と不要ファイルの整理を段階的に実施する。

---

## 現行テンプレート構成（調査時点）

### アクティブなテンプレート

| ファイル名 | 機能 | 課題 |
|-----------|------|------|
| `production_list.html` | 公演一覧 | なし |
| `production_detail.html` | 公演詳細 | なし |
| `production_form.html` | 公演作成フォーム | なし |
| `production_edit_modal.html` | 公演情報編集モーダル | Phase 2 で命名統一済み |
| `production_member_form.html` | 担当者追加・編集モーダル | 追加・編集・エラー表示を兼用するため現状維持 |
| `vehicle_assignment_list.html` | 車両手配管理一覧 | Phase 3 で URL 登録済み |
| `vehicle_assignment_edit_modal.html` | 車両手配編集モーダル | Phase 2 で命名統一済み |
| `process_block_edit_modal.html` | 工程ブロック編集モーダル | 命名は正確（基準） |
| `partials/processes_section.html` | 工程ブロック一覧セクション | なし |
| `partials/process_block_display.html` | 工程ブロック表示 | なし |
| `partials/process_block_form.html` | 工程ブロックフォーム | なし |
| `partials/_scripts_staff_days.html` | スタッフ日程 JS スクリプト | Phase 4 で命名統一済み |

### Phase 1 完了メモ

- 2026-03-14 に `src/templates/productions/unused/` と `src/apps/productions/unused/` を削除済み
- 削除前の確認で `views.py` に旧 ProcessDay 系ビューからの参照が残っていたため、未公開の旧ビュー群もあわせて除去した
- 現在、`productions` 配下に `unused/` 参照は存在しない

---

## Phase 1: `unused/` ディレクトリの完全削除

**ステータス**: 完了（2026-03-14）
**実績リスク**: 低
**実績作業量**: 小〜中（ファイル削除 + 旧ビュー参照の整理）

### 実施手順

```bash
# 1. productions 配下の unused 参照を確認
rg -n 'productions/unused|apps/productions/unused' src/apps/productions src/templates/productions

# 2. 旧 ProcessDay 系の未公開ビュー参照を削除

# 3. unused ディレクトリ配下のファイルを削除

# 4. 差分と整形を確認
git status
ruff check src/ --fix
ruff format src/
```

### 確認結果
- `src/apps/productions/views.py` から `productions/unused/...` 参照を削除済み
- `src/templates/productions/unused/` は削除済み
- `src/apps/productions/unused/` は削除済み

---

## Phase 2: テンプレートファイル名の統一（`_modal` サフィックス）

**ステータス**: 完了（2026-03-14）
**実績リスク**: 中
**実績作業量**: 小（リネーム + `views.py` 更新 + 回帰テスト追加）

### 命名規則（基準）

```
通常ページ    : production_list.html / production_detail.html
作成フォーム  : production_form.html
モーダル      : *_modal.html  ← process_block_edit_modal.html を基準とする
パーシャル    : partials/*.html
```

### 実施内容

| Before | After | 変更箇所 |
|--------|-------|---------|
| `production_edit_form.html` | `production_edit_modal.html` | `views.py` の `ProductionEditView.template_name` |
| `vehicle_assignment_form.html` | `vehicle_assignment_edit_modal.html` | `views.py` の `VehicleAssignmentEditView.template_name` |

### 実施手順

```bash
# テンプレートファイルのリネーム
cd src/templates/productions/
mv production_edit_form.html production_edit_modal.html
mv vehicle_assignment_form.html vehicle_assignment_edit_modal.html
```

`src/apps/productions/views.py` を以下のように更新：

```python
# ProductionEditView
template_name = 'productions/production_edit_modal.html'  # _form → _modal

# VehicleAssignmentEditView
template_name = 'productions/vehicle_assignment_edit_modal.html'  # _form → _modal
```

### 確認結果
- `src/apps/productions/views.py` のモーダル参照は新ファイル名へ更新済み
- `src/apps/productions/tests/test_active_routes.py` にテンプレート名を検証する回帰テストを追加済み
- `src/apps/productions/tests/test_process_block_edit.py` の表示確認を現行テンプレート構造に合わせて更新済み
- `vehicle_assignment` URL 登録前提の導線保証は Phase 3 で実施済み
- `docker` 上で `apps/productions/tests/` を実行し、14 件すべて成功を確認済み

---

## Phase 3: vehicle_assignment の URL 登録確認・修正

**ステータス**: 完了（2026-03-14）
**実績リスク**: 中
**実績作業量**: 小〜中（URL 追加 + 回帰テスト更新）

### 確認手順

```bash
# URL 名の参照を確認
grep -n 'vehicle_assignment' src/apps/productions/urls.py
grep -n 'vehicle_assignment' src/templates/productions/vehicle_assignment_list.html
```

### 実施内容

`src/apps/productions/urls.py` に以下を追加：

```python
path('<int:pk>/vehicle-assignments/', VehicleAssignmentListView.as_view(), name='vehicle_assignment_list'),
path('vehicle-assignments/<int:pk>/edit/', VehicleAssignmentEditView.as_view(), name='vehicle_assignment_edit'),
```

### 確認結果
- `src/apps/productions/urls.py` に `vehicle_assignment_list` / `vehicle_assignment_edit` を登録済み
- `src/apps/productions/tests/test_active_routes.py` をクライアント経由の実 URL テストへ更新済み
- `productions` 側の車両手配一覧と編集モーダルが URL reverse と GET の両方で利用可能になった
- `docker` 上で `apps/productions/tests/` を実行し、14 件すべて成功を確認済み

---

## Phase 4: 不活性テンプレートの整理

**ステータス**: 完了（2026-03-14）
**実績リスク**: 低
**実績作業量**: 小（未公開機能削除 + スクリプト partial rename + 回帰テスト追加）

### `production_member_bulk_form.html`

- URL 未登録で現在不活性
- 将来の「担当者一括追加」機能実装時に必要になる可能性あり
- **実施**: `ProductionMemberBulkAddView` と `production_member_bulk_form.html` を削除

### `partials/staff_days_app.html`

- JS スクリプトのインクルード用ファイル
- ファイル名が機能を反映していない
- **実施**: `partials/_scripts_staff_days.html` へリネームし、`production_detail.html` の include を更新

### 確認結果
- `src/apps/productions/views.py` から `ProductionMemberBulkAddView` を削除済み
- `src/templates/productions/production_member_bulk_form.html` を削除済み
- `src/templates/productions/partials/_scripts_staff_days.html` へ rename 済み
- `src/apps/productions/tests/test_active_routes.py` に詳細画面の script partial 回帰テストを追加済み
- `docker` 上で `apps/productions/tests/` を実行し、15 件すべて成功を確認済み

---

## 実施優先順位

| Phase | 優先度 | 理由 |
|-------|--------|------|
| Phase 1（unused 削除） | **最高** | リスクなし、即実施可能 |
| Phase 3（URL 確認） | **高** | 未登録なら本番 500 エラーのリスク |
| Phase 2（リネーム） | 中 | 命名統一、テスト後に実施 |
| Phase 4（個別整理） | 低 | 機能影響なし |

---

## 検証方法

各 Phase 実施後に以下を確認：

```bash
# 参照漏れ確認
git grep -rn 'production_edit_form\|vehicle_assignment_form' src/

# テスト実行
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

ブラウザ確認事項：
- 公演一覧 → 公演詳細 の遷移
- 公演情報編集モーダルの開閉・保存
- 工程ブロック編集モーダルの開閉・保存
- 車両手配一覧・編集モーダルの動作
