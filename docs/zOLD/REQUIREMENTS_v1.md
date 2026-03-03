# 1. プロジェクト概要
演劇・ミュージカル音響業務における人員および車両の申請・アサインを効率化する社内ツール。

## 最優先目標
管理負荷の削減

## 次点目標
・手配ミスの防止
・情報共有の円滑化

# 2. 設計思想（AI実装における絶対原則）

1. 公演担当者主導型とする。
2. 申請（Request）と実手配（Assignment）は物理的に別モデルとする。
3. 人員・車両は「時間帯占有管理」で扱う。
4. 占有時間はバッファ込みで計算する。
5. 物理削除は禁止し、論理削除フラグを使用する。
6. 設計変更が必要な場合は既存モデルを破壊せず拡張する。
7. 初期リリースでは外部API連携は実装しない。

# 3. システム構造
## 3.1 エンティティ構造
Performance
 └── PerformancePhase
       └── PhaseSlot
             ├── PhaseSlotRequest (1:1)
             └── PhaseSlotAssignment (1:1)
                   ├── StaffAssignment (M2M)
                   └── VehicleAssignment (FK)

# 4. モデル仕様
## 4.1 Performance
・title
・description
・is_active（論理削除）

## 4.2 PerformancePhase
・performance (FK)
・name
・order
・is_template_based (bool)
・is_active（論理削除）
※ フェーズは物理削除禁止

## 4.3 PhaseSlot
・performance_phase (FK)
・start_datetime
・end_datetime
・travel_buffer_before_minutes
・travel_buffer_after_minutes
・status（後述）
・is_active（論理削除）

# 5. 申請と実手配の分離
## 5.1 PhaseSlotRequest（申請内容）
・phase_slot (OneToOne)
・requested_staff_count
・requested_vehicle_type
・requested_vehicle_count
・notes

## 5.2 PhaseSlotAssignment（実手配）
・phase_slot (OneToOne)
・confirmed_at
・confirmed_by

## 5.3 StaffAssignment
・assignment (FK)
・staff (FK)

## 5.4 VehicleAssignment
・assignment (FK)
・vehicle (FK)
・is_external（外注車両フラグ）
※ 外注車両は占有管理対象外

# 6. 占有時間ロジック（固定仕様）
占有時間は以下で計算する：
occupied_start = start_datetime - travel_buffer_before_minutes
occupied_end   = end_datetime + travel_buffer_after_minutes

ダブルブッキング判定は
occupied時間帯の重複で行う。

# 7. ステータス管理
PhaseSlot.status は以下の状態を持つ：
・Draft
・Requested
・Assigned
・Locked

## 状態遷移ルール
Draft:
・Planner 編集可能

Requested:
・Planner 編集不可
・Manager が Assignment 作成可能

Assigned:
・Manager 編集可能

Locked:
・Admin のみ解除可能
・全ロール編集不可

# 8. 人員管理仕様
・人員は時間帯占有管理
・同一日に複数現場可
・occupied時間で衝突判定
・スキル属性でフィルタ可能

# 9. 車両管理仕様
## 管理対象
・会社所有車両のみ占有管理
・外注車両は占有対象外

## バッファ
・フェーズごとに手入力
・テンプレ初期値あり

# 10. フェーズ管理（A+Bハイブリッド）
・共通テンプレを公演作成時に展開
・特殊フェーズ追加可能
・削除は禁止（非表示化のみ）

# 11. PDF出力
初期リリース範囲：
・公演単位PDF
・日付単位PDF

# 12. ダッシュボード
## 管理者
・今日の工程
・明日の工程
・すみだ倉庫関連工程
・車両稼働状況
・人員稼働状況

## 個人
・自分のスケジュール

# 13. MVP範囲（初期リリース）
実装対象：
・公演作成
・フェーズ展開
・PhaseSlot管理
・Request登録
・Assignment登録
・ダブルブッキング検出
・PDF出力

実装しない：
・Google Maps API連携
・原価計算
・稼働率分析

# 14. 非機能要件
・Ubuntu 24.04
・Django
・Docker
・MySQL
・Apache Reverse Proxy
・LINE WORKS SSO
・同時接続 約30名