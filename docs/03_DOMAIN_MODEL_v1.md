## 公演手配管理システム

## Djangoドメインモデル仕様（Request / Assignment / Operation 分離版）

* * *

# 1. 目的

本ドキュメントは、AI実装時に **Djangoモデルの責務・境界・不変条件を迷いなく判断できる状態** を作るための仕様書である。

特に以下を明確にする。

-   何が申請（Request）か
-   何が確定実績（Assignment / Operation）か
-   どのモデルがどの責務を持つか
-   Lock時に何をスナップショット保存するか
-   何を変更禁止にするか

* * *

# 2. 設計の大原則

## 2.1 Request / Assignment / Operation 分離

### Request

制作側が入力する希望情報。  
後で管理側が組み替える前提の **断片情報**。

### Assignment

管理者が確定する割当結果。

### Operation

管理側が構築する実際の運行・作業単位。

* * *

## 2.2 Lock後は不変

Lock後は以下を変更してはいけない。

-   金額
-   単価適用結果
-   原価
-   工程内容
-   割当結果

再計算も禁止。

* * *

## 2.3 過去データ上書き禁止

-   単価履歴は上書きしない
-   スナップショットは更新しない
-   過去の確定内容は変更せず、必要なら差分レコード・再登録で吸収する

* * *

## 2.4 物理削除禁止

原則として物理削除はしない。  
削除が必要な場合は論理削除を採用する。

* * *

# 3. モデル全体像

Plain text

Performance  
 ├ Process  
 │   └ ProcessDay  
 │       ├ StaffRequest  
 │       └ VehicleRequest  
 │  
 ├ VehicleOperation  
 │   └ VehicleAssignment  
 │  
 ├ PerformancePosition  
 └ PerformanceFreelanceRate

人員側は

Plain text

StaffRequest → StaffAssignment

車両側は

Plain text

VehicleRequest → VehicleOperation → VehicleAssignment

で責務を分離する。

* * *

# 4. 公演・工程系モデル

* * *

## 4.1 Performance

### 役割

案件 / 公演のトップレベル集約。

### 主な責務

-   公演単位の工程管理
-   公演単位の人員・車両申請の親
-   管理UIでの集約単位

### 主なフィールド例

Python

実行する

title  
client_name  
start_date  
end_date  
status  
created_at  
updated_at

### 注意

-   人員・車両の申請は直接 Performance にぶら下げず、ProcessDay を経由する
-   管理側の VehicleOperation は Performance にぶら下げる

* * *

## 4.2 Process

### 役割

公演内の工程グループ。

### 例

-   稽古
-   劇場仕込み
-   本番
-   撤収

### 主なフィールド例

Python

実行する

performance = ForeignKey(Performance)  
title  
order

### 注意

-   1つの Process は複数の ProcessDay を持つ
-   タイトル重複回避が必要な場合は生成時に吸収する

* * *

## 4.3 ProcessDay

### 役割

実務上の **1工程日**。

### 主な責務

-   人員申請の単位
-   車両申請の単位
-   工程編集UIの単位

### 主なフィールド例

Python

実行する

process = ForeignKey(Process)  
process_type = ForeignKey(ProcessType)  
date  
location  
start_time  
end_time  
note  
order

### 注意

-   現在の申請UIは ProcessDay を中心に構築されている
-   1つの ProcessDay に複数の StaffRequest / VehicleRequest を持てる

* * *

# 5. 人員系モデル

* * *

## 5.1 PerformancePosition

### 役割

案件内で使うポジション定義。

### 例

-   チーフ
-   オペレーター
-   一般スタッフ

### 主な責務

-   人員申請の分類
-   単価適用の軸

* * *

## 5.2 StaffRequest

### 役割

制作側の人員希望。

### 概念

**1レコード = 1 ProcessDay × 1 Position の希望**

### 主なフィールド例

Python

実行する

process_day = ForeignKey(ProcessDay)  
position = ForeignKey(PerformancePosition)  
required_count  
note

### UI方針

-   ProcessDay単位で一括編集
-   前日コピーあり
-   同一 Position の重複は基本的に避ける

### 注意

-   これは希望人数であり、確定人数ではない
-   実人数は StaffAssignment 数で判断する

* * *

## 5.3 StaffAssignment

### 役割

管理者が確定した実際の人員割当。

### 主なフィールド例

Python

実行する

staff_request = ForeignKey(StaffRequest)  
user = ForeignKey(User)  
occupied_start  
occupied_end  
  
applied_rate_id  
applied_unit_price  
applied_allowance_total  
applied_total_amount  
applied_position_name  
applied_is_freelance  
locked_at

### スナップショット責務

Lock時に以下を保存する。

-   適用単価
-   手当合計
-   合計金額
-   ポジション名
-   外注/非外注属性

### 注意

-   occupied_start / occupied_end はダブルブッキング判定に使う
-   Lock後は再計算禁止

* * *

## 5.4 PerformanceFreelanceRate

### 役割

人員単価履歴。

### 主なフィールド例

Python

実行する

user = ForeignKey(User)  
position = ForeignKey(PerformancePosition)  
valid_from  
valid_to  
unit_price

### 制約

-   `user × position × 期間` の重複禁止
-   履歴上書き禁止

* * *

# 6. 車両系モデル

* * *

## 6.1 Vehicle

### 役割

車両マスタ。

### 主なフィールド例

Python

実行する

name  
vehicle_type  
ownership_type  
owner_user_id  
external_company_name  
is_active  
order  
note

### ownership_type

-   company
-   personal
-   external

### 注意

-   申請時は「車格」ではなく「車両名」で選ぶ運用を想定
-   管理側では車格・容量を見て差し替えることがある

* * *

## 6.2 VehicleRequest

### 役割

制作側の車両申請。

### 概念

**1レコード = 1便の希望**

### 主なフィールド

Python

実行する

process_day = ForeignKey(ProcessDay)  
requested_vehicle = ForeignKey(Vehicle)  
  
request_kind  
requested_time  
  
route_from  
route_to  
  
note

### request_kind の想定

-   load_in（搬入）
-   pickup（引き取り）
-   loading（荷積み）
-   unloading（荷降ろし）
-   other（その他）

### UI方針

-   ProcessDay単位で一括編集
-   行追加
-   行複製
-   直近コピー
-   1行 = 1目的 = 1時間 = 1ルート

### 注意

-   申請は実運行そのものではない
-   同じ車両を別時間・別目的で複数申請できる
-   route_from / route_to は自由入力 + 候補補助が基本

### 実務上の位置づけ

これは「最終配車結果」ではなく、

Plain text

この工程日に必要な便の断片

である。

* * *

## 6.3 VehicleOperation

### 役割

管理側が作る実際の運行工程。

### 概念

**1レコード = 管理側で扱う1つの運行工程**

### 主なフィールド例

Python

実行する

performance = ForeignKey(Performance)  
title  
  
requested_start  
requested_end  
scheduled_start  
scheduled_end  
  
route_from  
route_to  
description  
status

### 注意

-   VehicleRequest をそのままコピーするとは限らない
-   複数の VehicleRequest を統合して1つの VehicleOperation にできる
-   逆に1つの申請を分割する可能性もある

### 役割の違い

-   VehicleRequest = 申請断片
-   VehicleOperation = 実運行単位

* * *

## 6.4 VehicleAssignment

### 役割

実運行に対する車両確定。

### 主なフィールド例

Python

実行する

vehicle_operation = ForeignKey(VehicleOperation)  
vehicle = ForeignKey(Vehicle)  
driver_user = ForeignKey(User, null=True, blank=True)  
is_external_driver = BooleanField(default=False)  
  
applied_cost_amount  
applied_sales_amount  
actual_operation_count  
locked_at

### スナップショット責務

Lock時に以下を保存する。

-   確定原価
-   請求用金額
-   確定時の運行数
-   確定日時

### 注意

-   自社車 + 外注ドライバーの組み合わせを許容
-   Lock後に applied_cost_amount を変更しない

* * *

# 7. Request と Operation の責務分離

* * *

## 7.1 申請側（制作）

申請側は「必要な便」を出す。

例:

Plain text

倉庫 → 稽古場 / 搬入 / 09:00  
稽古場 → 劇場 / 引き取り / 18:00  
劇場 → 倉庫 / 荷降ろし / 21:00

ここでは、1台の実際のルートにまとまっていなくてもよい。

* * *

## 7.2 管理側（配車担当）

管理側は複数申請を見て、実際のルートに組み直す。

例:

Plain text

倉庫発  
→ 稽古場A 引き取り  
→ 稽古場B 引き取り  
→ 劇場C 荷降ろし  
→ 倉庫戻り

### 管理側で必要な操作

-   統合
-   分割
-   並び替え
-   実車割当
-   実時間確定

* * *

# 8. Lock時の不変条件

* * *

## 8.1 StaffAssignment

Lock後に変更してはいけない。

-   applied_unit_price
-   applied_allowance_total
-   applied_total_amount
-   applied_position_name

* * *

## 8.2 VehicleAssignment

Lock後に変更してはいけない。

-   applied_cost_amount
-   applied_sales_amount
-   actual_operation_count

* * *

## 8.3 共通

Lock後禁止事項

-   再計算
-   上書き
-   巻き戻し
-   マスタ再評価

必要なら差分処理で対応する。

* * *

# 9. ダブルブッキング判定

* * *

## 9.1 人員

判定対象:

Python

実行する

StaffAssignment.occupied_start  
StaffAssignment.occupied_end

### 判定軸

-   user
-   時間帯重複

* * *

## 9.2 車両

判定対象:

Python

実行する

VehicleOperation.scheduled_start  
VehicleOperation.scheduled_end  
VehicleAssignment.vehicle

### 判定軸

-   同一車両
-   時間帯重複

* * *

# 10. 論理削除方針

物理削除は禁止。  
削除が必要なモデルは将来的に以下を持つことを基本方針とする。

Python

実行する

is_active  
deleted_at  
deleted_by  
updated_by  
created_at  
updated_at

### 特に重要な対象

-   Process
-   ProcessDay
-   VehicleOperation

### 連動方針

親を論理削除した場合、子も連動して論理削除するのが基本。

* * *

# 11. AI実装時の必須注意点

1.  Lock処理は `transaction.atomic()` 必須
2.  必要箇所で `select_for_update()` を使う
3.  単価履歴の期間重複を禁止
4.  スナップショットを必ず保存
5.  Lock後再計算しない
6.  物理削除しない
7.  過去レコードを書き換えない
8.  Request と Operation を混同しない

* * *

# 12. 実装優先順位の考え方

### 先に作るべきもの

-   Process / ProcessDay
-   StaffRequest bulk edit
-   VehicleRequest bulk edit
-   直近コピー
-   route_from / route_to
-   request_kind

### 次に作るもの

-   StaffAssignment
-   VehicleOperation
-   VehicleAssignment
-   Lock
-   Costing

### 後でよいもの

-   高度な自動配車
-   ルート最適化
-   GPS連携
-   経営分析

* * *

# 13. 最終設計思想

Plain text

申請 = 希望  
割当 = 実績  
運行 = 管理側で構築  
Lock = 確定

そして最も重要なのはこれ。

**申請は断片、実運行は管理側で再構成する。**

