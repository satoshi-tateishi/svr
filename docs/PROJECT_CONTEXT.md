このプロジェクトの引き継ぎコンテキストです。

# プロジェクト概要
Django / Docker で、社内向けの「公演手配管理システム」を開発しています。
目的は、人員手配・車両配車・工程管理の一元化です。

# 技術スタック
- Django
- MySQL
- Docker
- HTMX
- Alpine.js
- TailwindCSS（CDN版）

# 設計思想（重要）
- Request / Assignment / Operation を分離
- Lock後は再計算禁止
- スナップショット保存
- 過去データ上書き禁止
- 物理削除禁止（論理削除前提）
- インラインCSS（style属性）禁止。Tailwind クラスのみ使用

# 現在の主要モデル構造

## 公演系
- **Production** - 公演プロジェクト（code, title, start_date, end_date, note, created_by）
  - `actual_start_date` / `actual_end_date` プロパティ: ProcessDay の最小/最大日付を返す
- **ProductionHoliday** - 休演日
- **ProductionMember** - 公演担当者
  - role: `sound_designer`（サウンドデザイナー）/ `chief`（チーフ）
  - start_date, end_date, note

## 工程系
- **ProcessType** - 工程種別マスター（color フィールドあり、ガントチャート用）
  - category: rehearsal / venue / warehouse / logistics / performance / other
- **Process** - 工程ブロック（大阪公演・稽古期間など。Production に属する）
- **ProcessDay** - 工程タスク（個別の1日単位の工程。日付・場所・開始終了時間・note）
- **ProductionTemplate** - 工程テンプレートプリセット（JSONField で構造保存）
- **Position** - 担当ポジションマスター

## 申請系
- **StaffRequest** - 人員申請
  - process_day, position, quantity, start_time, end_time, note
  - 同一ポジションを時間帯別に複数申請可能（unique_together なし）
- **VehicleRequest** - 車両申請（1レコード = 1便）
  - process_day, requested_vehicle, request_kind, requested_time, arrival_requested_time
  - route_from, route_to, note
- **VehicleAssignment** - 車両手配（管理側）
  - vehicle_request（OneToOne）, assigned_vehicle, status, note
  - status: `pending`（未対応）/ `reviewing`（調整中）/ `confirmed`（確定）

## VehicleRequest.request_kind の選択肢
- `load_in`（搬入）
- `pickup`（引き取り）
- `loading`（荷積み）
- `preload`（積み置き）
- `unloading`（荷降ろし）
- `other`（その他）

# UI構成・実装パターン

## レスポンシブ切り替え（モバイル/PC）
```html
{# モバイル: カードUI #}
<div class="space-y-3 lg:hidden">
  ...
</div>

{# PC: テーブルUI #}
<div class="hidden lg:block">
  ...
</div>
```

## PC全幅レイアウト
base.html の main に `{% block main_class %}` を持たせ、ページ側でオーバーライドする。
```html
{# 各テンプレートで宣言 #}
{% block main_class %}lg:max-w-none{% endblock %}
```
base.html の `<main>` はデフォルト `max-w-5xl`。全幅にしたいページだけ上記を追加する。

## テーブル列幅の固定
```html
<table class="min-w-full text-sm table-fixed">
  <thead>
    <tr>
      <th class="... w-36">工程</th>
      <th class="... w-48">場所</th>
      <th class="...">車両</th>  {# 幅指定なし → 残余を吸収 #}
    </tr>
  </thead>
```
`table-fixed` を使うと、コンテンツ量に依らず列ラインが揃う。

## 曜日カラーリング
```django
{% if day|date:'w' == '0' %}text-red-500    {# 日曜 #}
{% elif day|date:'w' == '6' %}text-blue-500  {# 土曜 #}
{% else %}text-gray-400{% endif %}
```
`date:'w'` = 0 が日曜、6 が土曜。LANGUAGE_CODE='ja' のため `date:"D"|slice:":1"` は日本語曜日1文字を返す。

## HTMX モーダル編集
- `hx-get` でモーダルコンテンツを取得し `hx-target="#modal"` に差し込む
- `hx-swap="innerHTML"` 標準
- 保存後は response 側で `HX-Redirect` または `HX-Trigger` を使う

## Alpine.js での bulk edit
- `x-data` で JSON 初期化 → `x-model` でフォームと連動
- hidden input の `requests_json` で bulk データを POST 送信

# 実装済み機能
- StaffRequest 一括編集（同一工程に複数ポジション・時間帯別）
- VehicleRequest 一括編集
- VehicleAssignment 管理（手配車両・状態・メモ）
- ProductionMember 管理（担当者・役割・期間）
- 人員の前日コピー
- 車両の直近コピー
- テンプレートから工程を一括生成（production_setup）
- 公演一覧 レスポンシブ UI（モバイル=カード / PC=テーブル）
- 公演詳細 レスポンシブ UI（モバイル=カード / PC=テーブル）

# 次に相談したいこと
（ここに今回の相談内容を書く）

# 現在のディレクトリ構成
```
src
├── apps
│   ├── accounts
│   │   ├── admin.py
│   │   ├── context_processors.py
│   │   ├── middleware.py
│   │   ├── migrations
│   │   ├── models.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── performances
│   │   ├── admin.py
│   │   ├── exceptions.py
│   │   ├── migrations
│   │   ├── models
│   │   ├── services
│   │   ├── tests
│   │   ├── urls.py
│   │   └── views.py
│   └── productions
│       ├── admin.py
│       ├── apps.py
│       ├── forms.py
│       ├── migrations
│       ├── models.py       ← Production / Process / ProcessDay / StaffRequest / VehicleRequest / VehicleAssignment / ProductionMember
│       ├── templates.py
│       ├── tests
│       ├── urls.py
│       └── views.py
├── config
│   ├── settings.py
│   ├── settings_test.py
│   ├── urls.py
│   └── wsgi.py
└── templates
    ├── base.html           ← {% block main_class %} 対応済み
    ├── performances
    │   ├── create.html
    │   ├── dashboard.html
    │   ├── detail.html
    │   ├── includes
    │   │   └── _gantt_chart.html   ← 曜日カラーリングの参考実装あり
    │   ├── list.html
    │   └── reports
    └── productions
        ├── partials
        │   ├── process_day_card.html    ← モバイル用カードUI
        │   ├── process_day_table.html   ← PC用テーブルUI（table-fixed・列幅固定済み）
        │   └── setup_block_card.html
        ├── process_day_form.html
        ├── production_detail.html       ← lg:max-w-none・レスポンシブ対応済み
        ├── production_form.html
        ├── production_list.html         ← lg:max-w-none・レスポンシブ対応済み
        ├── production_member_bulk_form.html
        ├── production_member_form.html
        ├── production_setup.html
        ├── staff_request_bulk_form.html
        ├── staff_request_form.html
        ├── vehicle_assignment_form.html
        ├── vehicle_assignment_list.html ← 車両手配管理テーブル
        └── vehicle_request_bulk_form.html
```

# 重要な制約・注意事項
- `src/` に `manage.py` は存在しない（テスト・マイグレーションは `docker run` で実行）
- Ruff チェック必須（リポジトリルートから実行）
- Tailwind CSS CDN 版のため `safelist` 不要
- `portal_jwt` クッキーで SSO（PortalJWTMiddleware）
- `UserProfile.portal_uuid` が外部参照の一意キー（user.id ではなく portal_uuid を使う）
