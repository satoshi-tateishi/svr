# ERD_v3.md

## 公演手配管理システム ERD（人員・配車・スナップショット統合版）

* * *

# 1. 改訂目的

-   **希望と実績の可視化**: 人員数および配車時間の「申請 vs 確定」を比較可能にする
-   **配車管理の統合**: 運行工程（Operation）と車輌割当（Assignment）の構造化
-   **Lock時の完全確定**: 車輌原価・人員単価・工程数のスナップショット保存
-   **不変性の維持**: Lock後の再計算・変更を厳絶に排除

* * *

# 2. 主要エンティティ一覧

-   Performance / PerformancePosition
-   **PhaseSlot**（人員・車輌の要求・枠管理）
-   **StaffAssignment**（人員の割当・金額スナップショット）
-   **Vehicle**（車輌マスタ：自社・自家用・外注）
-   **VehicleOperation**（運行工程：希望・確定時間保持）
-   **VehicleAssignment**（配車の割当・原価スナップショット）
-   PerformanceFreelanceRate（単価履歴）

* * *

# 3. ERD構造

## 3.1 PhaseSlot（作業枠・人員要求）

「いつ、何人必要か」という要求の起点。


```
PhaseSlot
- id (PK)
- performance_id (FK → Performance)
- phase_type (仕込/本番/撤収 等)
- status (Draft / Assigned / Locked)

# ---- 人員要求（比較用） ----
- requested_staff_count (希望人数)
- actual_staff_count (計算値: StaffAssignmentの数)

- created_at
- updated_at
```

## 3.2 StaffAssignment（人員割当・スナップショット）


```
StaffAssignment
- id (PK)
- phase_slot_id (FK → PhaseSlot)
- user_id (FK → User)
- position_id (FK → PerformancePosition)

# ---- 占有時間（ダブルブッキング判定用） ----
- occupied_start
- occupied_end

# ---- 🔒 Lock時スナップショット ----
- applied_rate_id (FK → PerformanceFreelanceRate)
- applied_unit_price
- applied_allowance_total
- applied_total_amount
- applied_position_name
- applied_is_freelance (boolean)
- locked_at (nullable)
```

* * *

## 3.3 Vehicle（車輌マスタ）


```
Vehicle
- id (PK)
- name (例: 習志野100 あ 12-34)
- vehicle_type (2tL / 4t / 乗用車 等)
- ownership_type (自社 / スタッフ自家用 / 外注)
- owner_user_id (FK → User, nullable: 自家用の場合)
- external_company_name (外注時の会社名)
- is_active (boolean)
```

## 3.4 VehicleOperation（運行工程・時間比較）

1案件に紐づく「1つの動き（倉庫→劇場など）」を管理。


```
VehicleOperation
- id (PK)
- performance_id (FK → Performance)
- title (例: 倉庫荷積・搬入)
- status (Draft / Assigned / Locked)

# ---- 時間の比較（申請 vs 確定） ----
- requested_start_datetime (申請者の希望)
- requested_end_datetime (申請者の希望)
- scheduled_start_datetime (管理者の確定)
- scheduled_end_datetime (管理者の確定)

- route_from
- route_to
- description
```

## 3.5 VehicleAssignment（配車割当・スナップショット）


```
VehicleAssignment
- id (PK)
- vehicle_operation_id (FK → VehicleOperation)
- vehicle_id (FK → Vehicle)
- driver_user_id (FK → User)
- is_external_driver (boolean: 外注ドライバーフラグ)

# ---- 🔒 Lock時スナップショット（原価・売上） ----
- applied_cost_amount (外注費/距離変動等、確定入力値)
- applied_sales_amount (案件側への請求額)
- locked_at
```

* * *

# 4. リレーション概要


```
Performance
  ├── PerformancePosition
  ├── PerformanceFreelanceRate
  ├── PhaseSlot (人員要求)
  │      └── StaffAssignment (人員確定 & 金額SS)
  └── VehicleOperation (運行工程・時間比較)
         └── VehicleAssignment (車輌確定 & 原価SS)
                └── Vehicle (車輌マスタ)
```

* * *

# 5. 運用ロジック

### ① 人員数の乖離確認

`PhaseSlot.requested_staff_count` と、紐づく `StaffAssignment` のレコード数をカウント比較することで、「3名希望に対し2名しか手配できていない」等のアラートが可能。

### ② 配車時間の乖離確認

`VehicleOperation` 内に `requested_` と `scheduled_` の両方を持つことで、制作側の希望からどれだけ時間が前後したかを抽出可能。

### ③ 🔒 Lock時の処理（トランザクション必須）

1.  **人員**: `StaffAssignment` に単価・手当・合計を書き込み。
2.  **配車**: `VehicleAssignment` に、その時点の走行距離や外注見積から算出した「確定原価」を書き込み。
3.  **完了**: 以降、マスタや工程を編集してもスナップショット側は参照専用となる。

* * *

# 6. データ整合性保証（配車）

| シナリオ | 挙動  |
| --- | --- |
| **自社車を外注が運転** | `Vehicle.ownership_type=自社` かつ `is_external_driver=True` として原価を計上。 |
| **Lock後の走行距離変更** | スナップショット（applied_cost_amount）は書き換えない。差分は別途調整用レコードを生成する運用。 |
| **ダブルブッキング** | `VehicleAssignment` の `scheduled_` 時間で車輌・人員の重複をバリデーション。 |





