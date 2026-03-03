# PRE_PRODUCTION_CHECKLIST_v2.md

## 公演手配管理システム 本番前チェックリスト（単価スナップショット対応版）

* * *

# 目的

本チェックリストは以下を保証するための最終確認用ドキュメントである：

-   ダブルブッキング事故防止
-   ロック破壊防止
-   単価確定の不可逆性保証（Snapshot方式）
-   権限突破防止
-   API連携事故防止
-   データ消失防止
-   金額改ざんリスク防止

* * *

# 1. 基本設定チェック

## 1.1 Django設定

-   DEBUG = False
-   SECRET_KEY 本番用ランダム値
-   ALLOWED_HOSTS 設定済み
-   SESSION_COOKIE_SECURE = True
-   CSRF_COOKIE_SECURE = True
-   SECURE_SSL_REDIRECT = True（HTTPS時）
-   SECURE_HSTS_SECONDS 設定済み

* * *

## 1.2 環境変数

-   .env をGit管理していない
-   DBパスワード強度確認
-   freee APIキー確認
-   board APIキー確認
-   SNAPSHOT_HASH_SALT設定済み

* * *

# 2. データベースチェック

## 2.1 マイグレーション

-   makemigrations 差分なし
-   migrate 成功
-   不要カラムなし
-   Snapshot OneToOne制約確認

* * *

## 2.2 インデックス確認

-   PhaseSlot.start_datetime index
-   PhaseSlot.status index
-   StaffAssignment.staff index
-   UnitPriceHistory.valid_from index
-   ApiTransmissionLog.status index
-   AuditLog.created_at index
-   CostSnapshot.performance_id index

* * *

## 2.3 トランザクション耐性

-   confirm_assignment で select_for_update 使用
-   lock_phase_slot atomic確認
-   snapshot生成もatomic内で実行

* * *

# 3. ダブルブッキング最終テスト

* * *

## 3.1 完全重複

-   同一スタッフ同時刻 → 拒否

* * *

## 3.2 部分重複

-   10:00-12:00 と 11:00-13:00 → 拒否

* * *

## 3.3 境界一致

-   10:00-12:00 と 12:00-14:00 → 許可

* * *

## 3.4 車両重複

-   同一車両重複 → 拒否

* * *

## 3.5 外部車両

-   is_external=True → 重複判定対象外

* * *

## 3.6 並列実行テスト

-   同時確定処理2件 → 片方のみ成功
-   DBロック待機確認

* * *

# 4. 単価スナップショット耐性チェック（重要）

* * *

## 4.1 Lock時Snapshot生成

-   CostSnapshot自動生成確認
-   snapshot_json保存確認
-   snapshot_hash生成確認
-   UnitPriceHistoryからの正しい取得確認

* * *

## 4.2 単価履歴変更後

-   UnitPriceHistory変更
-   既存Locked公演金額変化なし

* * *

## 4.3 Unlock→再Lock

-   Unlock理由必須
-   再Lock時Snapshot再生成
-   snapshot_hash変更確認
-   AuditLog生成確認

* * *

## 4.4 Snapshot改ざん耐性

-   DB直接変更後hash不一致検知可能
-   アプリからsnapshot更新不可

* * *

# 5. Locked耐性チェック

* * *

## 5.1 Locked後編集不可

-   Staff変更不可
-   Vehicle変更不可
-   時間変更不可
-   Request変更不可
-   単価変更不可

* * *

## 5.2 Locked解除

-   Adminのみ可能
-   理由必須
-   監査ログ生成確認
-   Unlock回数履歴保存確認

* * *

# 6. 権限突破チェック

* * *

## 6.1 Viewer操作

-   作成不可
-   更新不可
-   Assignment不可
-   Lock不可

* * *

## 6.2 Planner制限

-   他公演更新不可
-   他公演Lock不可

* * *

## 6.3 Editor横断

-   全公演更新可
-   Unlock可

* * *

## 6.4 API再送制御

-   Admin/Editorのみ可能

* * *

# 7. API連携チェック

* * *

## 7.1 Snapshot未生成時

-   API送信不可

* * *

## 7.2 成功時

-   ApiTransmissionLog.status = Success
-   snapshot_hash保存
-   監査ログ生成

* * *

## 7.3 失敗時

-   status = Failed
-   retry_count増加
-   PhaseSlotはLocked維持
-   Snapshot変更なし

* * *

## 7.4 retry上限

-   上限到達後自動停止
-   管理画面表示確認

* * *

# 8. 監査ログチェック

* * *

## 8.1 生成確認

-   Assignment確定時ログ生成
-   Lock実行時ログ生成
-   Unlock時ログ生成
-   Snapshot生成ログ
-   API失敗ログ

* * *

## 8.2 改ざん不可

-   AuditLog更新不可
-   AuditLog削除不可
-   DB権限でDELETE制限

* * *

## 8.3 before/after保存確認

-   JSON保存確認
-   変更差分確認可能

* * *

# 9. 同時アクセステスト

* * *

## 手動テスト（10人推奨）

-   同時Assignment登録
-   同時Lock試行
-   同時Unlock試行
-   DBエラーなし
-   デッドロックなし

* * *

# 10. Dockerチェック

* * *

## 10.1 コンテナ状態

-   web 起動中
-   db 起動中
-   redis 起動中
-   celery（導入済なら）起動中

* * *

## 10.2 ログ確認

-   Gunicornエラーなし
-   MySQL接続安定
-   OOMなし

* * *

# 11. Apacheチェック（ホスト側）

-   Proxy設定正常
-   HTTPS有効
-   リダイレクト正常
-   HSTS有効

* * *

# 12. バックアップ確認

* * *

-   手動mysqldump成功
-   Snapshot含めdump確認
-   復元テスト成功
-   日次バックアップcron設定済み
-   7日分以上保持確認

* * *

# 13. セキュリティ最終確認

* * *

-   MySQL外部公開なし
-   Dockerポート最小化
-   ufwで80/443のみ開放
-   rootログイン制限
-   fail2ban設定（可能なら）
-   管理画面IP制限（可能なら）

* * *

# 14. 本番リリース手順確認

* * *

1.  Git pull
2.  docker compose build
3.  docker compose up -d
4.  migrate確認
5.  ログ確認
6.  Snapshot生成テスト1件
7.  API送信テスト1件

* * *

# 15. リリース直後チェック（当日）

* * *

-   ダッシュボード表示確認
-   Snapshot金額表示確認
-   APIエラーなし
-   監査ログ生成確認
-   ログ肥大化なし
-   サーバー負荷確認

* * *

# 16. 緊急ロールバック手順

* * *

## アプリロールバック

-   旧コンテナイメージ保持
-   docker compose down
-   旧バージョン起動
-   migrate巻き戻し確認

* * *

## DBロールバック

-   dump復元
-   Snapshot整合性確認
-   hash再検証

* * *

# 最低合格ライン（v2）

以下を満たせばリリース可：

-   ダブルブッキング完全防止
-   Locked後変更不可
-   Snapshot保存済み
-   snapshot_hash整合
-   単価履歴変更で金額変動なし
-   API失敗時実績維持
-   監査ログ完全生成

* * *

# 総評（v2）

このチェックリストは：

-   金額事故耐性あり
-   法的防御力あり
-   小規模企業適正レベル
-   1人情シス運用可能
-   過剰すぎないが甘くない設計

