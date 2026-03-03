# REQUIREMENTS_v4.md

## 公演手配管理システム（運用強化版）

* * *

# 1. プロジェクト目的

## 最優先

管理負荷を減らす

## 次点

-   手配ミスをなくす
-   情報共有を楽にする

## 優先度低

-   経営データ可視化

* * *

# 2. 責務の境界（明文化）

自作アプリは「確定実績」までを責務とする。

金額計算・税計算・社会保険計算などの  
法的責任を伴う最終計算はSaaS側の責務とする。

-   社員給与の最終確定責任：freee人事労務
-   外注請求管理の最終確定責任：board

自作アプリ側は実績データを正確に送信することに責任を持つ。

* * *

# 3. 設計原則（絶対遵守）

1.  公演担当者主導型とする。
2.  Request と Assignment は物理的に別モデルとする。
3.  占有時間はバッファ込みで管理する。
4.  物理削除は禁止（is_active による論理削除）。
5.  既存モデルの破壊的変更は禁止。拡張は新規モデル追加で行う。
6.  system_role と performance_role は完全に独立させる。
7.  SaaSの責務を侵害する機能は実装しない。

* * *

# 4. API連携失敗時のリカバリ設計

## 4.1 送信ログ管理

API送信履歴テーブルを持つ。

ApiTransmissionLog:

-   target_system (freee / board)
-   related_object_id
-   payload_snapshot (JSON保存)
-   status (Pending / Success / Failed)
-   retry_count
-   last_error_message
-   last_attempt_at

* * *

## 4.2 再送設計

-   Failed の場合は管理画面から手動再送可能
-   retry_count が一定回数を超えた場合はアラート表示
-   自動無限リトライは禁止
-   送信成功時のみ Success に更新

* * *

## 4.3 ロックとの関係

-   実績確定後にAPI送信
-   API失敗しても実績ロックは維持
-   再送のみ可能とする
-   実績内容の自動巻き戻しは禁止

* * *

# 5. ロール設計

## システムロール

Admin / Editor / General / Viewer

## 公演内ロール

Planner / Chief / Sub

両者は完全に独立した概念とする。  
判定時に混同してはならない。

* * *

# 6. 占有時間ロジック（固定仕様）

occupied_start = start_datetime - travel_buffer_before_minutes  
occupied_end = end_datetime + travel_buffer_after_minutes

ダブルブッキング判定は occupied時間帯の重複で行う。

* * *

# 7. ダッシュボード

## 個人

-   自分のスケジュール
-   自分が担当する公演のスケジュール
-   他公演のスケジュール（閲覧のみ）

## 管理者

-   今日の工程
-   明日の工程
-   車両稼働状況
-   人員稼働状況
-   API送信エラー一覧

* * *

# 8. MVP範囲

## 実装対象

-   公演作成
-   フェーズ展開
-   PhaseSlot管理
-   Request登録
-   Assignment登録
-   ダブルブッキング検出
-   実績確定ロック
-   SaaS API送信
-   APIログ管理

## 実装しない

-   Google Maps API連携
-   原価計算
-   経営分析ダッシュボード
-   税計算ロジック自作
-   会計仕訳機能
-   勤怠管理機能の完全内製化

* * *

# 9. やらないことリスト（重要）

1.  給与計算エンジンを自作しない。
2.  会計システムを自作しない。
3.  外注請求書PDFを自作しない（board側に任せる）。
4.  法改正対応ロジックを内製しない。
5.  単価を現場画面に表示しない。
6.  SaaSと同等機能を重複実装しない。
7.  スモールスタートを崩す大規模分析機能を初期実装しない。

* * *

# 10. 非機能要件

-   Ubuntu 24.04
-   Django
-   Docker
-   MySQL
-   Apache Reverse Proxy
-   LINE WORKS SSO
-   同時接続 約30名

