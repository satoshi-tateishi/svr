## 公演手配管理システム 権限実装設計書（Service / View / HTMX 対応版）

* * *

# 1. 目的

本書は、`PERMISSION_DESIGN_v4.md` で定義した権限仕様を  
Django アプリケーションへ安全に実装するための実装設計を定義する。

対象：

-   Service層での権限判定
-   View層での適用
-   HTMX モーダルへの対応
-   Queryset / UI の制御方針
-   Locked 状態との優先関係

* * *

# 2. 権限モデルの基本方針

本システムは **二層権限モデル** を採用する。

Plain text

System Role（UserProfile.role）  
+  
Production Role（ProductionMember.role）

* * *

## 2.1 System Role

`UserProfile.role`

-   `admin`
-   `editor`
-   `general`
-   `viewer`

* * *

## 2.2 Production Role

`ProductionMember.role`

-   `sound_designer`
-   `chief`

* * *

# 3. 実装原則

* * *

## 3.1 権限判定は Service 層に集約する

権限ロジックを View / Template に散らさない。

### NG

-   View ごとに個別に role 判定を書く
-   Template でのみ制御する
-   HTMX と通常画面で別々の判定を書く

### OK

-   `services/permissions.py` に集約
-   View は Service を呼ぶだけにする

* * *

## 3.2 View は UX 制御、Service はセキュリティ制御

### View

-   ボタン表示制御
-   エラーメッセージ
-   HTMX 向け応答

### Service

-   実行可否判定
-   オブジェクト単位権限
-   金額秘匿判定

* * *

## 3.3 権限と状態は別管理

権限があっても、`Locked` 状態なら更新不可。

判定順序：

1.  ログイン済みか
2.  対象が Locked でないか
3.  権限があるか
4.  入力値が妥当か

* * *

# 4. 権限責務の分離

* * *

## 4.1 閲覧権限

閲覧は比較的広く許可する。

### 方針

-   `admin` / `editor` / `general` / `viewer` すべて公演一覧を閲覧可能
-   `general` も担当外公演を閲覧可能
-   一覧で他作品が見えることを維持する

### 理由

-   社内の一体感
-   他案件の存在把握
-   他社員の動向把握
-   年間80作品程度で、一覧非表示にするメリットが小さい

* * *

## 4.2 編集権限

編集は強く制限する。

### `admin`

全編集可能

### `editor`

全公演の申請・手配編集可能

### `general`

自分が担当する公演のみ申請編集可能

条件：

-   `ProductionMember.user = current_user`
-   `ProductionMember.role in ['sound_designer', 'chief']`

### `viewer`

編集不可

* * *

# 5. Permission Service 一覧

推奨配置：

Plain text

apps/productions/services/permissions.py

* * *

## 5.1 システムロール判定

Python

実行する

is_admin(user)  
is_editor(user)  
is_general(user)  
is_viewer(user)

* * *

## 5.2 公演担当判定

Python

実行する

is_production_member(user, production, roles=None)

用途：

-   その公演に紐づく担当者か
-   role 条件付き判定

* * *

## 5.3 申請編集権限

Python

実行する

can_edit_requests(user, production)

許可条件：

-   `admin`
-   `editor`
-   その公演の `sound_designer`
-   その公演の `chief`

* * *

## 5.4 手配管理権限

Python

実行する

can_manage_assignments(user)

許可条件：

-   `admin`
-   `editor`

* * *

## 5.5 工程編集権限

Python

実行する

can_edit_process(user, production)

許可条件：

-   `admin`
-   `editor`
-   その公演の `sound_designer`
-   その公演の `chief`

* * *

## 5.6 金額閲覧権限

Python

実行する

can_view_costs(user)

許可条件：

-   `admin`
-   `editor`

* * *

## 5.7 閲覧可能判定

Python

実行する

can_view_production(user, production)

現時点では以下を返してよい。

-   ログイン済みユーザーなら True

将来必要なら拡張。

* * *

# 6. View Mixin 方針

共通の権限制御は Mixin 化する。

* * *

## 6.1 RequestEditPermissionMixin

対象：

-   `StaffRequestBulkEditView`
-   `VehicleRequestBulkEditView`

責務：

-   `ProcessDay` → `Production` を辿る
-   `can_edit_requests()` を呼ぶ
-   権限なし時のレスポンスを返す

* * *

## 6.2 AssignmentManagePermissionMixin

対象：

-   `VehicleAssignmentListView`
-   `VehicleAssignmentEditView`
-   将来の `StaffAssignmentView`

責務：

-   `can_manage_assignments()` を呼ぶ

* * *

## 6.3 ProcessEditPermissionMixin

対象：

-   `ProcessDayEditView`
-   `ProcessDayCreateView`

責務：

-   `can_edit_process()` を呼ぶ

* * *

# 7. HTMX 時の権限拒否レスポンス

本システムは HTMX モーダルを多用するため、  
通常リクエストと HTMX リクエストで応答を分ける。

* * *

## 7.1 HTMX の場合

-   モーダル内にエラーメッセージを返す
-   403 ステータスを返してもよい
-   UIは既存トーンに合わせる

例：

Plain text

この公演の申請を編集する権限がありません。

* * *

## 7.2 通常リクエストの場合

-   `HttpResponseForbidden`
-   または detail/list に戻してメッセージ表示

* * *

# 8. Queryset 制御方針

現時点では **一覧は広く見せる**。

* * *

## 8.1 公演一覧

### 方針

-   `general` でも全公演表示
-   `viewer` でも全公演表示
-   担当外公演は編集導線のみ制御

### 理由

-   他作品の存在把握を維持する
-   社員としての一体感を損なわない

* * *

## 8.2 将来のUI改善方針

必要なら一覧画面で、担当外公演に対して

-   グレーアウト気味の表示
-   編集ボタン非表示
-   バッジ表示（担当外）

を追加する。

ただし現時点では必須ではない。

* * *

# 9. Object-level Permission 方針

権限判定は基本的に `Production` 単位で行う。

### 理由

-   `ProcessDay`
-   `StaffRequest`
-   `VehicleRequest`
-   `VehicleAssignment`

はいずれも最終的に `Production` に属するため。

つまり、各オブジェクトは

Plain text

Object -> ProcessDay -> Process -> Production

または

Plain text

Object -> VehicleRequest -> ProcessDay -> Process -> Production

を辿って判定する。

* * *

# 10. 金額秘匿の実装方針

金額情報は **Templateで隠すだけでは不十分**。

必ず以下のいずれかで制御する。

-   Service層
-   APIレスポンス生成時
-   Serializer相当処理

権限がない場合：

-   `None`
-   `null`
-   フィールド自体を返さない

のいずれかで制御する。

* * *

# 11. Locked 状態との優先順位

更新系処理では必ず

Plain text

Locked 判定  
→ 権限判定  
→ バリデーション

の順で判定する。

理由：

-   Locked は全ロール共通で強い制約
-   権限があっても変更不可にする必要がある

* * *

# 12. 最初に権限制御を入れる対象

優先順位：

## 第一優先

-   `StaffRequestBulkEditView`
-   `VehicleRequestBulkEditView`

## 第二優先

-   `VehicleAssignmentListView`
-   `VehicleAssignmentEditView`

## 第三優先

-   `ProcessDayEditView`
-   `ProcessDayCreateView`

* * *

# 13. UI 表示制御の方針

UI では権限に応じて編集導線を制御するが、  
**サーバー側の制御が本体**である。

### 例

-   申請編集ボタンを出すか
-   車両管理ボタンを出すか
-   金額列を表示するか

ただし UI 制御だけに依存してはいけない。

* * *

# 14. 監査のための今後の推奨項目

将来、申請・手配系モデルに追加推奨：

-   `created_by`
-   `updated_by`

理由：

-   誰が仮申請したか追える
-   editor による代理入力を説明できる
-   トラブル時の責任追跡ができる

* * *

# 15. 禁止事項

1.  Templateだけで権限制御すること
2.  HTMX側だけ特別処理して Service 判定を省略すること
3.  `general` の担当外公演を一覧から即非表示にすること
4.  金額を frontend 上だけ hidden にすること
5.  Locked を bypass すること

* * *

# 16. 現時点の実務対応まとめ

### editor

-   全公演の申請編集可能
-   全公演の手配管理可能

### general

-   全公演閲覧可能
-   自分の担当公演のみ申請編集可能

### viewer

-   全公演閲覧可能
-   編集不可

### admin

-   全操作可能

* * *

# 17. 最終まとめ

本システムの権限モデルは次で実装する。

Plain text

System Role  
  + Production Role  
  + Locked State  
  = Final Permission

特に重要な方針：

-   一覧は広く見せる
-   編集は厳しく制御する
-   HTMX モーダルも Service 判定で守る
-   `general` の担当外公演は隠さず、まずは見せる

