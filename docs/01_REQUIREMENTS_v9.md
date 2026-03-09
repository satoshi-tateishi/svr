# REQUIREMENTS_v9.md（AI実装用ミニマム仕様）

## 1. システム目的

本システムの目的は以下の3点。

### 最優先

**人員配置・配車・工程管理の管理負荷を削減する**

### 次点

-   ダブルブッキング防止
-   情報共有の可視化

### 優先度低

-   経営分析

* * *

# 2. システム責務

自作アプリは **確定実績管理まで** を責務とする。

金額の最終確定責任は SaaS 側。

ただし以下は自作アプリが責任を持つ。

### Lock時確定情報

-   人員原価
-   車両原価
-   手当合計
-   運行数

* * *

# 3. 設計の基本原則（絶対遵守）

1.  Request（希望） / Assignment（割当）分離
2.  Lock後は変更不可
3.  金額履歴は上書き禁止
4.  占有時間はバッファ込み
5.  物理削除禁止
6.  SaaSの計算ロジックを再実装しない
7.  スナップショット保存必須
8.  過去データを書き換えない

* * *

# 4. システム構造

Production  
 └ Process  
    └ ProcessDay  
        ├ StaffRequest  
        └ VehicleRequest

### Request層

制作が入力する希望。

### Assignment層

管理者が確定する実績。

* * *

# 5. 人員管理

## StaffRequest

制作側の希望。

### 主な内容

-   position
-   required_count
-   note

### UI

-   ProcessDay単位一括編集
-   前日コピー

* * *

## StaffAssignment

管理側の確定割当。

Lock時に以下を保存。

applied_unit_price  
applied_allowance_total  
applied_total_amount  
applied_position_name  
locked_at

* * *

# 6. 車両申請（VehicleRequest）

### 概念

**1レコード = 1便の申請**

申請は実運行ではなく **配車希望の断片情報**。

### 主フィールド

requested_vehicle  
request_kind  
requested_time  
route_from  
route_to  
note

### request_kind

例

-   荷積み
-   搬入
-   引き取り
-   荷降ろし
-   その他

### route

route_from  
route_to

例

倉庫 → 稽古場  
稽古場 → 劇場  
劇場 → 倉庫

* * *

# 7. 車両申請UI

### 基本構造

1行 = 1便

入力項目

申請車両  
申請種別  
出発地  
目的地  
配車希望時間  
備考

### UI機能

-   行追加
-   行複製
-   削除
-   **直近コピー**

* * *

# 8. 直近コピー

コピー対象

同一Production  
現在日より過去  
VehicleRequestが存在  
最も近いProcessDay

* * *

# 9. 配車管理（管理側）

申請は **実運行ではない**。

管理側は申請を元に **運行を再構成**する。

例

倉庫 → 稽古場A  
稽古場A → 稽古場B  
稽古場B → 劇場  
劇場 → 倉庫

### 管理側操作

-   申請の統合
-   分割
-   並び替え
-   車両割当

* * *

# 10. VehicleAssignment

Lock時に以下を保存。

applied_cost_amount  
applied_sales_amount  
actual_operation_count  
locked_at

* * *

# 11. ワークフロー

1 マスタ登録  
2 Request入力  
3 Assignment確定  
4 原価入力  
5 Lock  
6 SaaS連携

* * *

# 12. Lock処理

Lockは **トランザクション必須**

atomic  
select_for_update

Lock時に

-   人員金額
-   車両原価
-   工程数

をスナップショット保存。

* * *

# 13. 非機能要件

Ubuntu 24.04  
Django  
Docker  
MySQL  
LINE WORKS SSO  
AuditLog

* * *

# 14. やらないこと

-   単価履歴上書き
-   Lock後変更
-   SaaS税計算の再実装
-   GPS追跡

* * *

# 15. 最終設計思想

申請 = 希望  
割当 = 実績  
Lock = 確定

そして

**申請は断片、運行は管理側で構築する**

* * *

## AI実装時の最重要ルール

必ず守ること。

Lockはatomic  
select_for_update  
履歴上書き禁止  
スナップショット保存  
再計算禁止  
過去変更禁止
