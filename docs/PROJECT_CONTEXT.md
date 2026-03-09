# AI開発コンテキスト（引き継ぎ用）

このプロジェクトの引き継ぎコンテキストです。  
不足情報があれば推測せず質問してください。

* * *

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
-   portal SSO 連携
-   portal_uuid を外部参照キーとして使用

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

### 1. Request / Assignment / Operation 分離

Request  
  ↓  
Assignment（管理側調整）  
  ↓  
Operation（確定・実績）

例

VehicleRequest  
   ↓  
VehicleAssignment  
   ↓  
VehicleOperation（performances）

* * *

### 2. Lock後は再計算禁止

確定データは再計算しない。

* * *

### 3. スナップショット保存

確定時点のデータを保存。

* * *

### 4. 過去データ上書き禁止

履歴破壊を避ける。

* * *

### 5. 削除方針

基本：

-   物理削除禁止
-   論理削除前提

ただし以下は例外として物理削除あり

-   ProductionMember
-   管理用メタデータ

* * *

### 6. UI実装ルール

-   インラインCSS禁止
-   Tailwindクラスのみ使用

* * *

### 7. 権限制御

`UserProfile.system_role`（システム全体）と `ProductionMember.role`（公演単位）の2層で制御。

全判定ロジックは `productions/services/permissions.py` に集約。
View には Mixin（`RequestEditPermissionMixin` / `AssignmentManagePermissionMixin`）経由で適用。
HTMX リクエストには HTML 形式の 403 を返す（`permission_response.py`）。

権限マトリクス：

| 操作 | admin | editor | ProductionMember (SD/Chief) | general/viewer |
|------|-------|--------|----------------------------|----------------|
| 手配申請編集 | ✓ | ✓ | ✓ | ✗ |
| 手配管理 | ✓ | ✓ | ✗ | ✗ |
| コスト閲覧 | ✓ | ✓ | ✗ | ✗ |
| 公演閲覧 | ✓ | ✓ | ✓ | ✓ |

* * *

# 開発フェーズ

MVP実装後期。

完了済み：

-   管理UI改善
-   PC表示の最適化
-   手配管理機能の整備
-   最小権限制御の導入（Permission Service / Mixin）

現在の主な作業：

-   手配担当者向け UI の構築

* * *

# 主要モデル構造

## 公演系

### Production

公演プロジェクト

フィールド：

code  
title  
start_date  
end_date  
note  
created_by

プロパティ：

actual_start_date  
actual_end_date

ProcessDay の最小 / 最大日付を返す。

* * *

### ProductionHoliday

休演日

* * *

### ProductionMember

公演担当者

role

sound_designer  
chief

フィールド

user  
role  
start_date  
end_date  
note

同一人物が複数役割を持つことを許可。

* * *

## 工程系

### ProcessType

工程種別マスター

フィールド

name  
category  
color

category

rehearsal  
venue  
warehouse  
logistics  
performance  
other

* * *

### Process

工程ブロック

例

大阪公演  
稽古期間  
ツアー

Production に属する。

* * *

### ProcessDay

工程タスク（1日単位）

フィールド

date  
location  
start_time  
end_time  
note

* * *

### ProductionTemplate

工程テンプレート

JSONFieldで構造保存。

* * *

### Position

担当ポジションマスター

* * *

## 申請系

### StaffRequest

人員申請

process_day  
position  
quantity  
start_time  
end_time  
note

同一ポジションを時間帯別に複数申請可能。

unique 制約なし。

* * *

### VehicleRequest

車両申請  
**1レコード = 1便**

フィールド

process_day  
requested_vehicle  
request_kind  
requested_time  
arrival_requested_time  
route_from  
route_to  
note

* * *

### VehicleAssignment

車両手配（管理側）

vehicle_request (OneToOne)  
assigned_vehicle  
status  
note

status

pending  
reviewing  
confirmed

* * *

# VehicleRequest.request_kind

load_in  
pickup  
loading  
preload  
unloading  
other

* * *

# モデルリレーション

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

# レスポンシブ切り替え

HTML

{# モバイル #}  
<div class="space-y-3 lg:hidden">  
</div>  
  
{# PC #}  
<div class="hidden lg:block">  
</div>

* * *

# PC全幅レイアウト

base.html

<main class="max-w-5xl mx-auto px-4 py-8 {% block main_class %}{% endblock %}">

ページ側

{% block main_class %}lg:max-w-none{% endblock %}

これにより  
PCページだけ幅制限を解除可能。

* * *

# テーブル列幅固定

HTML

<table class="min-w-full text-sm table-fixed">

例

<th class="w-36">工程</th>  
<th class="w-48">場所</th>  
<th>車両</th

幅未指定列が残余を吸収。

* * *

# 曜日カラーリング

django

{% if day|date:'w' == '0' %}  
text-red-500  
{% elif day|date:'w' == '6' %}  
text-blue-500  
{% else %}  
text-gray-400  
{% endif %}

* * *

# HTMXモーダル編集

パターン

hx-get → モーダル表示  
hx-post → 保存  
HX-Redirect → 更新

* * *

# Alpine.js bulk edit

x-data  
x-model  
hidden input JSON

で一括編集。

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

* * *

# 現在のディレクトリ構成

src  
├── apps  
│   ├── accounts  
│   ├── performances  
│   └── productions  
├── config  
└── templates

詳細は以下。

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
│       │   └── permission_response.py
│       └── templates
│           ├── partials
│           │   ├── process_day_card.html
│           │   ├── process_day_table.html
│           │   └── setup_block_card.html
│           ├── production_detail.html
│           ├── production_list.html
│           ├── production_setup.html
│           └── vehicle_assignment_list.html

* * *

# 重要な制約

-   manage.py は src に存在しない
-   docker run で実行
-   Ruff チェック必須
-   Tailwind CDN
-   safelist不要

* * *

# SSO

Portal SSO 使用。

portal_jwt cookie

PortalJWTMiddleware が検証。

* * *

# 外部キー

ユーザー参照は

user.id  
ではなく  
  
UserProfile.portal_uuid

を使用する場合がある。

* * *

# 次に相談したいこと

（ここに質問を書く）

* * *

# 補足

不足情報があれば推測せず質問してください。

