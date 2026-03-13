# 権限実装設計書

## 1. 現行権限モデル

権限は二層です。

```text
UserProfile.system_role
+ ProductionMember.role
```

### `UserProfile.system_role`

- `admin`
- `editor`
- `general`
- `viewer`

### `ProductionMember.role`

- `sound_designer`
- `chief`

## 2. 実装場所

- 権限判定関数: `apps/productions/services/permissions.py`
- エラーレスポンス: `apps/productions/services/permission_response.py`
- View 適用:
  - `RequestEditPermissionMixin`
  - `ProcessEditPermissionMixin`
  - `AssignmentManagePermissionMixin`

## 3. 判定仕様

### 閲覧

現状は `LoginRequiredMixin` ベースで、一覧・詳細への到達自体は広く許可されています。一覧の表示制限を行う専用サービスは未実装です。

### 申請編集

`can_edit_requests(user, production)`

許可:

- `admin`
- `editor`
- 当該 `production` の `sound_designer`
- 当該 `production` の `chief`

### 工程ブロック編集

`ProcessEditPermissionMixin` は内部で `can_edit_requests()` を使います。つまり申請編集権限と同じです。

### 手配管理

`can_manage_assignments(user)`

許可:

- `admin`
- `editor`

## 4. 実装済み関数

- `is_admin(user)`
- `is_editor(user)`
- `is_general(user)`
- `is_viewer(user)`
- `is_production_member(user, production, roles=None)`
- `can_edit_requests(user, production)`
- `can_manage_assignments(user)`
- `can_edit_process(user, production)`
- `can_view_costs(user)`

## 5. HTMX 時の応答

`permission_denied_response()` の仕様:

- HTMX リクエストなら赤系の HTML 断片 + HTTP 403
- 通常リクエストなら `HttpResponseForbidden`

## 6. まだ未実装の点

- テンプレート側の表示制御統一
- `performances` 側 View への同等の権限サービス適用
- Lock 状態と権限の複合判定共通化
- オブジェクト単位のコスト秘匿レスポンス
