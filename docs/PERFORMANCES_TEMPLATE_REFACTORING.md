# performances テンプレート整理メモ

> 作成日: 2026-03-14
> 対象: `src/templates/production_management/` および `src/apps/performances/`

---

## 背景・目的

`performances` では、現行のダッシュボード系テンプレートとは別に、未公開の旧 Performance CRUD / レポート向けテンプレートが `unused/` 配下に残っていた。
また、`views.py` には `performances/list.html`・`create.html`・`detail.html` を参照する旧ビューが残っていたが、対応テンプレートは現行配置に存在せず、`urls.py` にも未登録だった。

本整理では、公開中のダッシュボード導線だけを残し、未公開の旧テンプレート・旧ビュー・旧参照を削除して整合を回復した。

---

## 現役テンプレート

現役テンプレートの配置先は `src/templates/production_management/` とする。

| ファイル名 | 用途 |
|-----------|------|
| `dashboard.html` | 乖離ダッシュボード |
| `production_vehicle_assignment_dashboard.html` | Production 横断の車両手配管理一覧 |
| `production_vehicle_assignment_form.html` | Production 横断の車両手配編集モーダル |

---

## 削除内容

### テンプレート

- `src/templates/performances/unused/` 配下を削除
- 対象:
  - `list.html`
  - `create.html`
  - `detail.html`
  - `includes/_template_setup.html`
  - `includes/_gantt_chart.html`
  - `includes/_phase_modal.html`
  - `includes/_vehicle_modal.html`
  - `includes/_scripts.html`
  - `reports/performance_report.html`
  - `reports/financial_report.html`

### アプリ側

- `src/apps/performances/unused/` 配下を削除
- `src/apps/performances/views.py` から未公開の旧 Performance CRUD / 工程編集 / 運行工程編集ビューを削除
- `performances:detail` / `performances:create` など未登録 URL 前提の参照を解消

---

## 確認結果

- 現役の公開導線は `performances:dashboard`、`performances:production_vehicle_assignments`、`performances:production_vehicle_assignment_edit` のみ
- `performances/unused` および `performances/reports/*` 参照は削除済み
- 現役テンプレートは `src/templates/performances/` から `src/templates/production_management/` へ移動済み
- `src/apps/performances/tests/test_active_routes.py` を追加し、現役導線の回帰を確認
- `src/apps/productions/tests/test_active_routes.py` も合わせて実行し、dashboard 連携が壊れていないことを確認
- `docker` 上で以下を実行し、成功を確認

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
  python -m pytest apps/performances/tests/ apps/productions/tests/test_active_routes.py -v --no-header -p no:logging
```

```bash
ruff check src/ --fix
ruff format src/
```
