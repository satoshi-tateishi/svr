# API / View Contract 仕様

## 1. 基本方針

### `productions`

- 一覧・詳細は通常テンプレート
- 編集 UI は HTMX モーダル中心
- 成功時は `HX-Redirect`
- エラー時は同テンプレートを再描画

### `performances`

- 通常の Django View 中心
- PDF 出力はバイナリレスポンス

## 2. 共通レスポンスルール

### HTMX 成功

```python
response = HttpResponse()
response['HX-Redirect'] = reverse(...)
return response
```

### HTMX 権限エラー

- `HX-Request: true` の場合は HTML 断片 + 403
- 通常リクエストは `HttpResponseForbidden`

### JSON 補助 API

- 前日コピーやテンプレート一覧は `JsonResponse`

## 3. `productions` 契約

### 画面系

- `GET /productions/`
  - name: `productions:list`
  - 公演一覧

- `GET /productions/create/`
  - name: `productions:create`
  - 公演作成画面

- `GET /productions/<pk>/`
  - name: `productions:detail`
  - 公演詳細

- `GET|POST /productions/<pk>/setup/`
  - name: `productions:setup`
  - 工程構成セットアップ

- `GET /productions/<pk>/processes-partial/`
  - name: `productions:processes_partial`
  - 工程一覧部分描画

### 工程日編集

- `GET|POST /productions/process-day/<pk>/edit/`
  - name: `productions:process_day_edit`

- `GET|POST /productions/<production_id>/process-day/add/`
  - name: `productions:process_day_add`

### 人員申請

- `GET|POST /productions/process-day/<day_pk>/staff-request/`
  - name: `productions:staff_request_edit`
  - 旧 UI 互換

- `GET|POST /productions/process-day/<day_pk>/staff-requests/`
  - name: `productions:staff_requests_bulk_edit`
  - `requests_json` を送信

- `GET /productions/process-day/<day_pk>/staff-requests/previous/`
  - name: `productions:staff_requests_previous`
  - JSON: `source_date`, `requests`

### 車両申請

- `GET|POST /productions/process-day/<day_pk>/vehicle-requests/`
  - name: `productions:vehicle_requests_bulk_edit`
  - `requests_json` を送信

- `GET /productions/process-day/<day_pk>/vehicle-requests/previous/`
  - name: `productions:vehicle_requests_previous`
  - JSON: `source_date`, `requests`

### 車両手配

- `GET /productions/<pk>/vehicle-assignments/`
  - name: `productions:vehicle_assignment_list`

- `GET|POST /productions/vehicle-request/<pk>/assignment/`
  - name: `productions:vehicle_assignment_edit`

### 担当者

- `GET|POST /productions/<production_pk>/members/add/`
  - name: `productions:member_add`

- `GET|POST /productions/members/<pk>/edit/`
  - name: `productions:member_edit`

- `POST /productions/members/<pk>/delete/`
  - name: `productions:member_delete`

### 工程ブロック

- `GET|POST /productions/block/<process_pk>/edit/`
  - name: `productions:block_edit`

- `POST /productions/block/<process_pk>/delete/`
  - name: `productions:block_delete`

### テンプレート API

- `GET /productions/templates/api/`
  - name: `productions:template_api`
  - JSON 配列を返す

## 4. `productions` POST ペイロード要約

### `staff_requests_bulk_edit`

- hidden input `requests_json`
- 各要素:
  - `position_id`
  - `quantity`
  - `start_time`
  - `end_time`
  - `note`

### `vehicle_requests_bulk_edit`

- hidden input `requests_json`
- 各要素:
  - `requested_vehicle_id`
  - `request_kind`
  - `requested_time`
  - `arrival_requested_time`
  - `route_from`
  - `route_to`
  - `note`

## 5. `performances` 契約

- `GET /performances/`
  - name: `performances:list`

- `GET /performances/dashboard/`
  - name: `performances:dashboard`

- `GET|POST /performances/create/`
  - name: `performances:create`

- `GET /performances/<pk>/`
  - name: `performances:detail`

- `POST /performances/<pk>/delete/`
  - name: `performances:delete`

- `POST /performances/<pk>/apply-template/`
  - name: `performances:apply_template`

- `POST /performances/<pk>/phases/add/`
  - name: `performances:phase_add`

- `POST /performances/phases/<pk>/delete/`
  - name: `performances:phase_delete`

- `POST /performances/phases/<pk>/update/`
  - name: `performances:phase_update`

- `POST /performances/<pk>/phases/reorder/`
  - name: `performances:phase_reorder`

- `POST /performances/<pk>/vehicles/add/`
  - name: `performances:vehicle_operation_add`

- `POST /performances/vehicles/<pk>/delete/`
  - name: `performances:vehicle_operation_delete`

- `POST /performances/<pk>/vehicles/batch-delete/`
  - name: `performances:vehicle_operation_batch_delete`

- `GET /performances/<pk>/report/performance/`
  - name: `performances:report_performance`

- `GET /performances/<pk>/report/financial/`
  - name: `performances:report_financial`

## 6. 旧設計との差分

- `productions` は JSON API 群ではなく Django View + HTMX 契約が中心
- `performances` の Lock API はまだ公開 View 化されていない
- 監査ログ API は未実装
