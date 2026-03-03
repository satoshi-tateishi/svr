# IMPLEMENTATION_ROADMAP_8WEEKS_v2.md

## 公演手配管理システム 実装ロードマップ（8週間プラン・単価スナップショット対応版）

* * *

# 全体方針（v2）

優先順位：

1.  ダブルブッキング防止
2.  ロック耐性
3.  単価確定（スナップショット）
4.  権限突破防止
5.  API失敗耐性
6.  UIは最後

* * *

# Week 1：基盤構築

## 目標

安全な開発基盤完成

## 作業

-   Djangoプロジェクト作成
-   apps構成分離
-   Dockerローカル構築
-   MySQL接続確認
-   Redis導入
-   カスタムUser設定
-   Ruff導入
-   pytest導入
-   pre-commit設定

## 成果物

-   起動確認
-   マイグレーション成功
-   CI通過
-   Docker起動確認

* * *

# Week 2：コアモデル + 単価基盤

## 目標

ERD完全反映

## 実装

-   Performance
-   PerformanceMember
-   PhaseSlot
-   StaffAssignment
-   Vehicle
-   VehicleAssignment
-   UnitPriceHistory（追加）
-   CostSnapshot（追加）
-   ApiTransmissionLog
-   AuditLog

## 必須テスト

-   unique制約
-   valid_from重複検知
-   negative buffer validation
-   OneToOne Snapshot制約

* * *

# Week 3：Service層（基礎 + 単価判定）

## 目標

業務ロジック骨格完成

## 実装

-   PerformanceService
-   PhaseSlotService
-   ScheduleConflictService
-   UnitPriceService
-   有効期間判定ロジック
-   calculate_occupied_time()

## テスト

-   占有時間境界値
-   重複判定正常／異常
-   単価有効期間境界値
-   単価未存在時挙動

ここが金額事故防止の基盤。

* * *

# Week 4：Assignment確定 + 競合制御

## 目標

ダブルブッキング完全制御

## 実装

-   AssignmentService.confirm_assignment()
-   select_for_update導入
-   Staff / Vehicle重複判定
-   Transaction完全設計

## テスト

-   完全重複
-   部分重複
-   境界一致
-   並列処理テスト（簡易）

事故防止の核心。

* * *

# Week 5：Lock + スナップショット + 監査ログ

## 目標

不可逆処理完成

## 実装

-   LockService
-   CostSnapshotService
-   snapshot_hash生成
-   Unlock→再Lock対応
-   AuditService拡張
-   performance_role_snapshot保存

## テスト

-   Lock時snapshot生成
-   hash整合性
-   Unlock理由必須
-   再Lock時再生成
-   Locked後更新禁止

ここで「法的防御力」が完成。

* * *

# Week 6：API統合 + 非同期準備

## 目標

SaaS境界完成

## 実装

-   ApiIntegrationService
-   失敗時ステータス保持
-   retry上限制御
-   Celery導入（準備のみでも可）
-   Snapshot未生成時送信禁止

## テスト

-   成功
-   失敗
-   再送
-   retry上限
-   Locked維持確認

API失敗でも実績は壊れない。

* * *

# Week 7：UI実装（最低限）

## 目標

業務運用可能

## 画面

-   公演一覧
-   PhaseSlot一覧
-   Request画面
-   Assignment画面
-   Snapshot金額表示
-   APIエラー一覧
-   監査ログ簡易表示

## ポイント

-   Service側で最終防衛
-   UIは表示制御のみ

* * *

# Week 8：本番準備 + 運用耐性確認

## 目標

安全リリース可能状態

## 作業

-   Docker本番構築（v2構成）
-   Apacheリバースプロキシ
-   HTTPS化
-   index追加
-   日次バックアップ自動化
-   監査ログ肥大化確認
-   Snapshot負荷確認

## 最終試験

-   ダブルブッキング試験
-   Lock→Unlock→再Lock試験
-   単価変更後再Lock試験
-   API障害試験
-   同時アクセス試験（10人程度）

* * *

# 並行してやること

## 毎週

-   pytest全通過
-   マイグレーション整理
-   index確認
-   AuditLog容量確認

* * *

# リスク管理（v2）

* * *

## リスク1：単価誤適用

対策：

-   有効期間境界値テスト
-   snapshot_json保存

* * *

## リスク2：Lock後金額変更

対策：

-   Snapshot方式採用
-   再Lock時再生成

* * *

## リスク3：監査ログ肥大化

対策：

-   index設計
-   アーカイブ設計

* * *

## リスク4：API二重送信

対策：

-   TransmissionLog状態管理
-   retry制限

* * *

# マイルストーン（v2）

| 週   | 到達状態 |
| --- | --- |
| 2   | DB + 単価基盤完成 |
| 4   | 事故防止完成 |
| 5   | 金額確定・改ざん耐性完成 |
| 6   | SaaS連携完成 |
| 8   | 本番安全運用可能 |

* * *

# MVP定義（v2）

-   ダブルブッキングゼロ
-   Locked後変更不可
-   Snapshot保存済み
-   snapshot_hash一致
-   API失敗ログ可視化
-   権限突破不可

これを満たせば「事故らないシステム」。

* * *

# 8週間後の次段階

-   月次請求自動生成
-   freee金額自動突合
-   監査ログUI強化
-   Celery完全非同期化
-   経営ダッシュボード

* * *

# 総評（v2）

この8週間プランは：

-   1人開発現実的
-   金額事故耐性あり
-   法的防御力あり
-   小規模企業最適
-   将来拡張可能

