## 公演手配管理システム ERD

（Request / Assignment / Operation 分離 + 配車ルート対応版）

* * *

# 1. 改訂目的

今回の改訂では以下を実現する。

### ① 申請レイヤーと運用レイヤーの分離

制作が入力する **Request（希望）** と  
管理者が確定する **Assignment / Operation（実績）** を明確に分離する。

### ② 配車ルートの表現力強化

車両申請に

route_from  
route_to

を追加し、以下のようなルートを表現可能にする。

倉庫 → 稽古場  
稽古場 → 劇場  
劇場 → 倉庫

### ③ Lock時の完全スナップショット

Lock時に

-   人員単価
-   手当
-   車両原価
-   運行数

を保存し、以降は変更不可とする。

* * *

# 2. 主要エンティティ一覧

## 公演・工程

-   Performance
-   Process
-   ProcessDay

## 人員

-   StaffRequest
-   StaffAssignment
-   PerformancePosition
-   PerformanceFreelanceRate

## 車両

-   Vehicle
-   VehicleRequest
-   VehicleOperation
-   VehicleAssignment

* * *

# 3. ERD構造

* * *

# 3.1 Performance（公演）

Performance  
- id (PK)  
- title  
- client  
- start_date  
- end_date  
- status  
- created_at  
- updated_at

公演単位のトップエンティティ。

* * *

# 3.2 Process（工程）

Process  
- id (PK)  
- performance_id (FK → Performance)  
- name  
- sort_order

例

稽古  
劇場仕込み  
本番  
撤収

* * *

# 3.3 ProcessDay（工程日）

ProcessDay  
- id (PK)  
- process_id (FK → Process)  
- date  
- location  
- status (Draft / Assigned / Locked)

1つの工程に複数日が存在可能。

Process  
 └ ProcessDay

* * *

# 4. 人員管理

* * *

# 4.1 StaffRequest（人員申請）

制作側が入力する **希望人数**。

StaffRequest  
- id (PK)  
- process_day_id (FK → ProcessDay)  
- position_id (FK → PerformancePosition)  
- required_count  
- note

### UI

ProcessDay単位で **一括編集可能**

機能

-   前日コピー
-   行追加
-   行削除

* * *

# 4.2 StaffAssignment（人員割当）

管理者が確定する **実際の配置**。

StaffAssignment  
- id (PK)  
- staff_request_id (FK → StaffRequest)  
- user_id (FK → User)  
  
# 占有時間（ダブルブッキング判定）  
- occupied_start  
- occupied_end  
  
# 🔒 Lock時スナップショット  
- applied_rate_id  
- applied_unit_price  
- applied_allowance_total  
- applied_total_amount  
- applied_position_name  
- applied_is_freelance  
- locked_at

* * *

# 4.3 PerformanceFreelanceRate（単価履歴）

PerformanceFreelanceRate  
- id (PK)  
- user_id  
- position_id  
- valid_from  
- valid_to  
- unit_price

履歴保持（上書き禁止）。

* * *

# 5. 車両管理

* * *

# 5.1 Vehicle（車両マスタ）

Vehicle  
- id (PK)  
- name  
- vehicle_type  
- ownership_type  
- owner_user_id  
- external_company_name  
- is_active

ownership_type

自社  
スタッフ自家用  
外注

* * *

# 5.2 VehicleRequest（車両申請）

制作側が入力する **配車希望**。

**1レコード = 1便**

VehicleRequest  
- id (PK)  
- process_day_id (FK → ProcessDay)  
  
- requested_vehicle_id (FK → Vehicle)  
  
- request_kind  
    (荷積 / 搬入 / 引き取り / 荷降ろし / その他)  
  
- requested_time  
  
- route_from  
- route_to  
  
- note

### 例

倉庫 → 稽古場  
種別: 搬入  
時間: 09:00

稽古場 → 倉庫  
種別: 引き取り  
時間: 18:00

* * *

# 5.3 VehicleOperation（運行工程）

管理者が作成する **実際の運行工程**。

VehicleOperation  
- id (PK)  
- performance_id (FK → Performance)  
  
- title  
- description  
  
- requested_start_datetime  
- requested_end_datetime  
  
- scheduled_start_datetime  
- scheduled_end_datetime  
  
- route_from  
- route_to

1つの運行工程は

倉庫 → 稽古場  
稽古場 → 劇場  
劇場 → 倉庫

などを表す。

* * *

# 5.4 VehicleAssignment（配車確定）

実際の車両割当。

VehicleAssignment  
- id (PK)  
- vehicle_operation_id (FK → VehicleOperation)  
- vehicle_id (FK → Vehicle)  
  
- driver_user_id  
- is_external_driver  
  
# 🔒 Lock時スナップショット  
- applied_cost_amount  
- applied_sales_amount  
- actual_operation_count  
- locked_at

* * *

# 6. リレーション

Performance  
 ├ PerformancePosition  
 ├ PerformanceFreelanceRate  
 │  
 ├ Process  
 │   └ ProcessDay  
 │        ├ StaffRequest  
 │        │    └ StaffAssignment  
 │        │  
 │        └ VehicleRequest  
 │  
 └ VehicleOperation  
      └ VehicleAssignment  
           └ Vehicle

* * *

# 7. 運用ロジック

* * *

## ① 人員不足検知

StaffRequest.required_count

と

StaffAssignment count

を比較し、不足を検知。

* * *

## ② 配車希望と確定時間の比較

VehicleOperationに

requested_start_datetime  
scheduled_start_datetime

を保持することで

**希望時間と確定時間の差分分析**が可能。

* * *

## ③ 🔒 Lock処理

Lockは **atomicトランザクション必須**。

処理内容

### 人員

StaffAssignment  
  applied_unit_price  
  applied_allowance_total  
  applied_total_amount

を書き込み。

### 車両

VehicleAssignment  
  applied_cost_amount  
  applied_sales_amount

を書き込み。

Lock後は

再計算禁止  
変更禁止

* * *

# 8. 配車整合性ルール

| シナリオ | 挙動  |
| --- | --- |
| 自社車を外注が運転 | `ownership_type=自社` + `is_external_driver=True` |
| Lock後の距離変更 | applied_cost_amount変更禁止 |
| ダブルブッキング | scheduled時間で検証 |

* * *

# 9. 配車設計思想

車両申請は **実運行ではない**。

VehicleRequest = 配車希望  
VehicleOperation = 実運行

管理側は

統合  
分割  
順序変更

を行い、実際のルートを作る。

例

倉庫 → 稽古場A  
稽古場A → 稽古場B  
稽古場B → 劇場  
劇場 → 倉庫

* * *

# 10. Lock原則

Lock後  
- 金額変更不可  
- 工程変更不可  
- 再計算不可

過去データを書き換えない。

