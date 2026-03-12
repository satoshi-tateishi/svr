# プロジェクト概要

Django / Docker で、社内向けの **公演手配管理システム** を開発しています。

目的：

-   人員手配
-   車両配車
-   工程管理

を一元化すること。

対象ユーザーは **約30名の社内スタッフ**です。

* * *

# 技術スタック

-   Django
-   MySQL
-   Docker
-   HTMX
-   Alpine.js
-   TailwindCSS（CDN版）

* * *

# Django App責務

## accounts

認証・ユーザー管理

-   UserProfile
-   Portal SSO 連携
-   portal\_uuid を外部参照キーとして使用

## productions

本システムの中心ドメイン

-   公演管理
-   工程管理
-   人員申請
-   車両申請
-   車両手配
-   権限制御（Permission Service）

## performances

実績・オペレーション層

本番時のスナップショットや確定データを管理  
（Request / Assignment の先の Operation 層）

* * *

# 設計思想（重要）

このプロジェクトでは以下を強く意識しています。

## 1\. Request / Assignment / Operation 分離

Plain text

Request  
  ↓  
Assignment（管理側調整）  
  ↓  
Operation（確定・実績）

例：

Plain text

VehicleRequest  
   ↓  
VehicleAssignment  
   ↓  
VehicleOperation（performances）

* * *

## 2\. Lock後は再計算禁止

確定データは再計算しない。

* * *

## 3\. スナップショット保存

確定時点のデータを保存する。

* * *

## 4\. 過去データ上書き禁止

履歴破壊を避ける。

* * *

## 5\. 削除方針

基本：

-   物理削除禁止
-   論理削除前提

ただし以下は例外として物理削除あり：

-   ProductionMember
-   一部の管理用メタデータ

* * *

## 6\. UI実装ルール

-   インラインCSS禁止
-   Tailwindクラスのみ使用

* * *

## 7\. 権限制御

`UserProfile.system_role`（システム全体）と  
`ProductionMember.role`（公演単位）の2層で制御。

全判定ロジックは `productions/services/permissions.py` に集約。  
View には Mixin（`RequestEditPermissionMixin` / `AssignmentManagePermissionMixin`）経由で適用。  
HTMX リクエストには HTML 形式の 403 を返す（`permission_response.py`）。

権限マトリクス：

| 操作  | admin | editor | ProductionMember (SD/Chief) | general/viewer |
| --- | --- | --- | --- | --- |
| 手配申請編集 | ✓   | ✓   | ✓   | ✗   |
| 手配管理 | ✓   | ✓   | ✗   | ✗   |
| コスト閲覧 | ✓   | ✓   | ✗   | ✗   |
| 公演閲覧 | ✓   | ✓   | ✓   | ✓   |

補足：

-   `general` ユーザーでも **公演一覧は全件閲覧可能**
-   ただし **担当外公演の編集は不可**
-   「見えるが触れない」方針を採用している

* * *

# 開発フェーズ

MVP実装後期。

完了済み：

-   管理UI改善
-   PC表示の最適化
-   車両手配管理機能の整備
-   最小権限制御の導入（Permission Service / Mixin）
-   公演期間表示を `ProcessDay` ベースに寄せる設計整理
-   production\_setup の入力保持改善
-   production\_detail の「手配書イメージ」寄せ改善（Phase 1 / 2）

現在の主な作業：

-   **手配担当者向け UI の構築**
-   **production\_detail を主画面に寄せる Phase 3 以降の整理**

* * *

# 主要モデル構造

## 公演系

### Production

公演プロジェクト

フィールド：

-   code
-   title
-   start\_date
-   end\_date
-   note
-   created\_by

プロパティ：

-   actual\_start\_date
-   actual\_end\_date

`ProcessDay` の最小 / 最大日付を返す。  
ただし工程未作成時は `start_date / end_date` をフォールバック表示する。

補足：

-   `start_date / end_date` は **仮期間** として扱う思想
-   工程作成後は `ProcessDay` の min/max が実表示に優先される

* * *

### ProductionHoliday

休演日

* * *

### ProductionMember

公演担当者

role:

-   sound\_designer
-   chief

フィールド：

-   user
-   role
-   start\_date
-   end\_date
-   note

同一人物が複数役割を持つことを許可。  
期間を持つことで途中交代も表現可能。

* * *

## 工程系

### ProcessType

工程種別マスター

フィールド：

-   name
-   category
-   color

category:

-   rehearsal
-   venue
-   warehouse
-   logistics
-   performance
-   other

* * *

### Process

工程ブロック（紙フォームの1セクション単位）

例：

-   稽古場仕込み
-   すみだものチェック
-   本番機材スタンバイ
-   劇場仕込み

Production に属する。

追加フィールド（0018 migration）：

-   `block_key`: テンプレートブロックキー（rehearsal_setup 等）
-   `sumida_required`: すみだ便必要フラグ（null=未設定）
-   `assistant_required`: 助っ人必要フラグ（null=未設定）

* * *

### ProcessDay

工程タスク（1日単位）

フィールド：

-   date
-   location
-   start\_time
-   end\_time
-   note

補足：

-   今後の UI 上では **1ブロック = 1工程** として扱う思想が強い
-   `production_detail` 上ではこの単位が「手配書の1項目」になる想定

* * *

### ProductionTemplate

工程テンプレート

JSONFieldで構造保存。

補足：

-   内部的には残す
-   UIでは「テンプレート」より **工程をまとめて追加する補助機能** として見せる方向

* * *

### Position

担当ポジションマスター

* * *

## 申請系

### StaffRequest

人員申請

-   process\_day
-   position
-   quantity
-   start\_time
-   end\_time
-   note

同一ポジションを時間帯別に複数申請可能。  
unique 制約なし。

* * *

### VehicleRequest

車両申請  
**1レコード = 1便**

フィールド：

-   process\_day
-   requested\_vehicle
-   request\_kind
-   requested\_time
-   arrival\_requested\_time
-   route\_from
-   route\_to
-   note

* * *

### VehicleAssignment

車両手配（管理側）

-   vehicle\_request (OneToOne)
-   assigned\_vehicle
-   status
-   note

status:

-   pending
-   reviewing
-   confirmed

* * *

# VehicleRequest.request\_kind

-   load\_in
-   pickup
-   loading
-   preload
-   unloading
-   other

* * *

# モデルリレーション

Plain text

Production  
 └ Process  
     └ ProcessDay  
         ├ StaffRequest  
         └ VehicleRequest  
               └ VehicleAssignment

* * *

# UI構成

このプロジェクトは **モバイルファースト**です。

* * *

## レスポンシブ切り替え

HTML

{# モバイル #}  
<div class\="space-y-3 lg:hidden"\>  
</div>  
  
{# PC #}  
<div class\="hidden lg:block"\>  
</div>

* * *

## PC全幅レイアウト

base.html

HTML

<main class\="max-w-5xl mx-auto px-4 py-8 {% block main\_class %}{% endblock %}"\>

ページ側

django

{% block main\_class %}lg:max-w-none{% endblock %}

これにより、PCページだけ幅制限を解除可能。

* * *

## テーブル列幅固定

HTML

<table class\="min-w-full text-sm table-fixed"\>

例：

HTML

<th class\="w-36"\>工程</th>  
<th class\="w-48"\>場所</th>  
<th>車両</th>

幅未指定列が残余を吸収する。

* * *

## 曜日カラーリング

django

{% if day|date:'w' == '0' %}  
text-red-500  
{% elif day|date:'w' == '6' %}  
text-blue-500  
{% else %}  
text-gray-400  
{% endif %}

* * *

## HTMXモーダル編集

基本パターン：

-   `hx-get` → モーダル表示
-   `hx-post` → 保存
-   `HX-Redirect` → 更新

* * *

## Alpine.js bulk edit

-   `x-data`
-   `x-model`
-   hidden input + JSON

で一括編集する。

* * *

# 現在のUI方針（重要）

## production\_setup の位置づけ

`production_setup.html` は現在も存在するが、  
**主画面ではなく補助画面**として扱う方向。

用途：

-   工程をまとめて追加したいとき
-   雛型から初期構成を作りたいとき
-   一括で工程ブロックを組みたいとき

つまり、

-   setup = 補助的な構成編集画面
-   detail = 主画面

という思想で移行中。

* * *

## production\_detail の位置づけ

`production_detail.html` を  
**手配書イメージの主画面**として育てている。

現在の方向性：

-   工程一覧ではなく **工程手配書**
-   1工程 = 1ブロック
-   日付ごとにセクション化
-   人員 / 車両は「申請機能」ではなく「手配書の記載項目」として自然に見せる
-   将来的には **ブロック全体タップで工程編集モーダル** を主導線にしたい

* * *

# 実装済み機能

-   StaffRequest 一括編集
-   VehicleRequest 一括編集
-   VehicleAssignment 管理
-   ProductionMember 管理
-   人員の前日コピー
-   車両の直近コピー
-   テンプレートから工程生成
-   公演一覧レスポンシブUI
-   公演詳細レスポンシブUI
-   権限制御（Permission Service / Mixin）
-   production\_setup の入力復元
-   production\_setup にプレビュー / 手配書イメージの考え方を導入
-   production\_detail の empty state 改善
-   production\_detail の工程ブロックUI改善（Phase 2）

* * *

# 現在の設計上の到達点

## Phase 1

-   文言整理
-   setup の役割を補助機能寄りに調整
-   detail の empty state を「手配書の器」に改善

## Phase 2

-   production\_detail を「工程手配書」らしく改善
-   日付ヘッダー / ブロック見せ方 / カード情報密度の改善

## Phase 3（設計レビュー済み、実装はこれから / または途中）

目標：

-   公演作成後の遷移先を `setup` から `detail` へ変更
-   detail を最初から主画面として使う
-   setup は補助画面として残す
-   empty state から
    
    -   工程をまとめて追加
    -   まず1件だけ追加  
        の両導線を持たせる
-   公演作成フォームで「仮期間」を明示
-   `start_date` は必須化を検討 / 推奨

* * *

# 現在のディレクトリ構成

Plain text

src  
├── apps  
│   ├── accounts  
│   ├── performances  
│   └── productions  
│       ├── models.py  
│       ├── views.py  
│       ├── forms.py  
│       ├── mixins.py  
│       ├── services/  
│       │   ├── permissions.py  
│       │   └── permission\_response.py  
│       └── templates  
│           ├── partials  
│           │   ├── process\_day\_card.html  
│           │   ├── process\_day\_table.html  
│           │   └── setup\_block\_card.html  
│           ├── production\_detail.html  
│           ├── production\_form.html  
│           ├── production\_list.html  
│           ├── production\_setup.html  
│           └── vehicle\_assignment\_list.html  
├── config  
└── templates

* * *

# 重要な制約

-   `manage.py` は src に存在しない
-   `docker run` / コンテナ経由で実行する
-   Ruff チェック必須
-   Tailwind CDN 版
-   safelist 不要

* * *

# SSO

Portal SSO 使用。

-   `portal_jwt` cookie
-   `PortalJWTMiddleware` が検証

* * *

# 外部キー / 外部参照

ユーザー参照は場面によって

-   `user.id`  
    ではなく
-   `UserProfile.portal_uuid`

を使う場合がある。

* * *

# 直近で重要な実務上のUI思想

-   紙ベースの手配書は分かりやすい
-   ただし紙の見た目をそのまま再現するのではなく、  
    **紙の思考構造**
    
    -   全体を俯瞰
    -   必要なところだけ編集
    -   ブロック単位で扱う  
        を Web UI に落とす
-   フォームを順番に埋めるより、  
    **手配書イメージを主画面にして、ブロックをタップして編集**  
    に寄せたい

* * *

# 次に相談したいこと

（ここに質問を書く）

* * *

# 補足

不足情報があれば推測せず質問してください。

