# REQUIREMENTS.md

## 公演手配管理システム（AI実装強化版）

------------------------------------------------------------------------

# 1. プロジェクト目的

### 最優先

管理負荷を減らす

### 次点

-   手配ミスをなくす
-   情報共有を楽にする

### 優先度低

-   経営データ可視化

------------------------------------------------------------------------

# 2. 設計原則（絶対遵守）

1.  公演担当者主導型とする。
2.  申請（Request）と実手配（Assignment）は物理的に別モデルとする。
3.  占有時間はバッファ込みで管理する。
4.  物理削除は禁止（is_active による論理削除）。
5.  既存モデルを破壊的変更しない。拡張は新規モデル追加で行う。
6.  外部API連携は初期リリースでは実装しない。
7.  system_role と performance_role
    は完全に独立した概念であり、混同してはならない。

------------------------------------------------------------------------

# 3. ロール設計

## 3.1 システムロール（全体権限）

User.system_role: - Admin - Editor - General - Viewer

## 3.2 公演内ロール（公演ごとに変動）

PerformanceMember: - performance (FK) - user (FK) - role - Planner -
Chief - Sub

同一ユーザーが複数公演で異なるroleを持つことを許容する。

------------------------------------------------------------------------

# 4. エンティティ構造

Performance └── PerformancePhase └── PhaseSlot ├── PhaseSlotRequest
(1:1) └── PhaseSlotAssignment (1:1) ├── StaffAssignment (M2M) └──
VehicleAssignment (FK)

------------------------------------------------------------------------

# 5. モデル仕様

## Performance

-   title
-   description
-   is_active

## PerformancePhase

-   performance (FK)
-   name
-   order
-   is_template_based
-   is_active

## PhaseSlot

-   performance_phase (FK)
-   start_datetime
-   end_datetime
-   travel_buffer_before_minutes
-   travel_buffer_after_minutes
-   status
-   is_active

------------------------------------------------------------------------

# 6. 申請と実手配の分離

## PhaseSlotRequest

-   phase_slot (OneToOne)
-   requested_staff_count
-   requested_vehicle_type
-   requested_vehicle_count
-   notes

## PhaseSlotAssignment

-   phase_slot (OneToOne)
-   confirmed_at
-   confirmed_by

## StaffAssignment

-   assignment (FK)
-   staff (FK)

## VehicleAssignment

-   assignment (FK)
-   vehicle (FK)
-   is_external

※ 外注車両は占有管理対象外

------------------------------------------------------------------------

# 7. 占有時間ロジック（固定仕様）

occupied_start = start_datetime - travel_buffer_before_minutes
occupied_end = end_datetime + travel_buffer_after_minutes

ダブルブッキング判定は occupied時間帯の重複で行う。

------------------------------------------------------------------------

# 8. ステータス管理

Draft: Planner / Chief 編集可能

Requested: Planner / Chief 編集不可
Manager（Editor以上）Assignment作成可能

Assigned: Manager（Editor以上）編集可能

Locked: Adminのみ解除可能 全ロール編集不可

------------------------------------------------------------------------

# 9. ダッシュボード

## 個人

-   自分のスケジュール
-   自分が担当する公演のスケジュール
-   他の公演のスケジュール（閲覧のみ）

## 管理者

-   今日の工程
-   明日の工程
-   車両稼働状況
-   人員稼働状況

------------------------------------------------------------------------

# 10. 人員管理

-   時間帯占有管理
-   同日複数現場可
-   occupied時間で衝突判定

------------------------------------------------------------------------

# 11. 車両管理

-   会社所有車両のみ占有管理
-   外注車両は占有対象外
-   バッファはフェーズごとに手入力（テンプレ初期値あり）

------------------------------------------------------------------------

# 12. MVP範囲

実装対象: - 公演作成 - フェーズ展開 - PhaseSlot管理 - Request登録 -
Assignment登録 - ダブルブッキング検出 - PDF出力

実装しない: - Google Maps API連携 - 原価計算 - 稼働率分析

------------------------------------------------------------------------

# 13. 非機能要件

-   Ubuntu 24.04
-   Django
-   Docker
-   MySQL
-   Apache Reverse Proxy
-   LINE WORKS SSO
-   同時接続 約30名
