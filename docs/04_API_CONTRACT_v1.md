## 公演手配管理システム

## API / View Contract 仕様（HTMX + Django View ベース）

* * *

# 1. 目的

本ドキュメントは、フロントエンド（HTMX / Alpine.js）と Django View 間の契約を固定し、以下を防ぐことを目的とする。

-   画面差し替え時の不整合
-   JSON構造の揺れ
-   bulk edit の保存形式のブレ
-   直近コピー API の返却仕様のブレ
-   HTMXモーダルのターゲット・swap方法の不一致

* * *

# 2. 基本方針

## 2.1 UI構成

本システムの申請UIは以下の構成を基本とする。

-   一覧画面: 通常 Django Template
-   編集UI: **HTMX モーダル**
-   モーダル内部状態管理: **Alpine.js**
-   保存: **HTMX POST**
-   保存成功後: **HX-Redirect**
-   バリデーションエラー時: **モーダルHTMLを再描画**

* * *

## 2.2 API種別

本システムでは API を次の2種類に分ける。

### A. HTML返却型

HTMXモーダル表示用。

例:

-   ProcessDay編集
-   StaffRequest一括編集
-   VehicleRequest一括編集

### B. JSON返却型

補助機能用。

例:

-   前日コピー
-   直近コピー

* * *

# 3. 共通ルール

## 3.1 HTMX モーダル

モーダルを開くエンドポイントは以下を満たすこと。

### GET

-   HTMLを返す
-   単独テンプレートとして描画可能
-   `#modal` に `innerHTML` で差し込める

### POST

-   成功時: `HX-Redirect` を返す
-   失敗時: 同じモーダルHTMLを返す

* * *

## 3.2 成功時レスポンス

成功時は以下を原則とする。

Python

実行する

response = HttpResponse()  
response["HX-Redirect"] = reverse(...)  
return response

### 理由

-   一覧再描画整合性を担保するため
-   部分差し替えより安全なため

* * *

## 3.3 バリデーションエラー

バリデーションエラー時は以下を原則とする。

-   HTTP 200でよい
-   同じテンプレートを再描画
-   エラーメッセージをテンプレート内に表示

* * *

## 3.4 Alpine.js の送信形式

bulk edit 系は hidden input に JSON 文字列を詰めて送る。

例:

HTML

<input type="hidden" name="requests_json" :value="JSON.stringify(requests)">

サーバー側では

Python

実行する

data_json = request.POST.get("requests_json", "[]")  
submitted_data = json.loads(data_json)

で受け取る。

* * *

# 4. ルーティング契約

以下は現在の標準ルール。

* * *

## 4.1 ProcessDay 編集

### GET

Plain text

process-day/<int:pk>/edit/

### name

Plain text

process_day_edit

### 用途

-   工程日基本情報の編集モーダル

* * *

## 4.2 StaffRequest 単票編集（互換維持用）

### GET / POST

Plain text

process-day/<int:day_pk>/staff-request/

### name

Plain text

staff_request_edit

### 用途

-   単票編集
-   旧UI互換用

* * *

## 4.3 StaffRequest 一括編集

### GET / POST

Plain text

process-day/<int:day_pk>/staff-requests/

### name

Plain text

staff_requests_bulk_edit

### 用途

-   人員手配一括編集モーダル

* * *

## 4.4 StaffRequest 前日コピー

### GET

Plain text

process-day/<int:day_pk>/staff-requests/previous/

### name

Plain text

staff_requests_previous

### 用途

-   過去の人員構成取得
-   JSON返却

* * *

## 4.5 VehicleRequest 一括編集

### GET / POST

Plain text

process-day/<int:day_pk>/vehicle-requests/

### name

Plain text

vehicle_requests_bulk_edit

### 用途

-   車両申請一括編集モーダル

* * *

## 4.6 VehicleRequest 直近コピー

### GET

Plain text

process-day/<int:day_pk>/vehicle-requests/previous/

### name

Plain text

vehicle_requests_previous

### 用途

-   実装名は previous のままでもよい
-   意味としては **直近の有効な車両申請を返す**
-   JSON返却

* * *

# 5. HTML返却型 Contract

* * *

# 5.1 ProcessDayEditView

## GET 入力

-   `pk`

## GET 出力

-   `productions/process_day_form.html`

## context

Python

実行する

{  
    "day": ProcessDay,  
    "form": ProcessDayForm,  
}

## POST 成功

-   `HX-Redirect: productions:detail`

## POST 失敗

-   同テンプレート再描画

* * *

# 5.2 StaffRequestBulkEditView

## GET 入力

-   `day_pk`

## GET 出力

-   `productions/staff_request_bulk_form.html`

## context

Python

実行する

{  
    "day": ProcessDay,  
    "initial_requests": [  
        {  
            "position_id": int,  
            "quantity": int,  
            "note": str,  
        }  
    ],  
    "positions": QuerySet[Position],  
}

## POST 入力

`requests_json`

### 期待JSON

JSON

[  
  {  
    "position_id": 1,  
    "quantity": 2,  
    "note": "サブ卓あり"  
  }  
]

## POST 成功

-   `HX-Redirect`

## POST 失敗 context

Python

実行する

{  
    "day": ProcessDay,  
    "positions": QuerySet[Position],  
    "initial_requests": submitted_data,  
    "error_message": str,  
}

* * *

# 5.3 VehicleRequestBulkEditView

## GET 入力

-   `day_pk`

## GET 出力

-   `productions/vehicle_request_bulk_form.html`

## context

Python

実行する

{  
    "day": ProcessDay,  
    "initial_requests": [  
        {  
            "requested_vehicle_id": int,  
            "request_kind": str,  
            "requested_time": "HH:MM" or "",  
            "route_from": str,  
            "route_to": str,  
            "note": str,  
        }  
    ],  
    "vehicles": QuerySet[Vehicle],  
}

## POST 入力

`requests_json`

### 期待JSON

JSON

[  
  {  
    "requested_vehicle_id": 1,  
    "request_kind": "pickup",  
    "requested_time": "18:00",  
    "route_from": "新宿村スタジオ",  
    "route_to": "赤堤倉庫",  
    "note": "倉庫戻し"  
  }  
]

## POST 成功

-   `HX-Redirect`

## POST 失敗 context

Python

実行する

{  
    "day": ProcessDay,  
    "vehicles": QuerySet[Vehicle],  
    "initial_requests": submitted_data,  
    "error_message": str,  
}

* * *

# 6. JSON返却型 Contract

* * *

# 6.1 StaffRequest 前日コピー

## endpoint

Plain text

staff_requests_previous

## method

GET

## 入力

-   `day_pk`

## 正常返却

JSON

{  
  "source_date": "2026/03/01",  
  "requests": [  
    {  
      "position_id": 1,  
      "quantity": 2,  
      "note": ""  
    }  
  ]  
}

## コピー元なし

JSON

{  
  "source_date": null,  
  "requests": []  
}

* * *

# 6.2 VehicleRequest 直近コピー

## endpoint

Plain text

vehicle_requests_previous

## method

GET

## 入力

-   `day_pk`

## 意味

-   同一 Production
-   現在日より過去
-   `vehicle_requests` が存在する ProcessDay
-   その中で最も近いもの

## 正常返却

JSON

{  
  "source_date": "2026/03/01",  
  "requests": [  
    {  
      "requested_vehicle_id": 1,  
      "request_kind": "pickup",  
      "requested_time": "18:00",  
      "route_from": "新宿村スタジオ",  
      "route_to": "赤堤倉庫",  
      "note": "倉庫戻し"  
    }  
  ]  
}

## コピー元なし

JSON

{  
  "source_date": null,  
  "requests": []  
}

* * *

# 7. フロントエンド契約

* * *

## 7.1 モーダルターゲット

すべてのモーダル系 HTMX GET は原則以下を使用。

HTML

hx-target="#modal"  
hx-swap="innerHTML"

* * *

## 7.2 モーダル内部POST

モーダル内部フォームの POST は原則以下。

### 通常

HTML

hx-post="..."  
hx-target="#modal-container"  
hx-swap="outerHTML"

### 理由

-   バリデーションエラー時にモーダル全体を差し替えるため

* * *

## 7.3 Alpine 初期化

HTMX差し替え後は Alpine を再初期化する必要がある。  
base.html 側で `htmx:afterSwap` を拾って `Alpine.initTree()` を行う前提。

* * *

## 7.4 bulk edit hidden input

### Staff

HTML

<input type="hidden" name="requests_json" :value="JSON.stringify(requests)">

### Vehicle

HTML

<input type="hidden" name="requests_json" :value="JSON.stringify(requests)">

送信前に `prepareSubmit()` で型を整える。

* * *

# 8. サーバー側バリデーション契約

* * *

## 8.1 StaffRequestBulkEditView

### 必須チェック

-   position_id が実在する
-   quantity >= 1
-   同一 ProcessDay 内で position 重複禁止

### 許可

-   position未選択行は無視

* * *

## 8.2 VehicleRequestBulkEditView

### 必須チェック

-   requested_vehicle_id が実在する
-   request_kind が許可値内
-   requested_time は空なら null 許可
-   route_from / route_to は trim 後保存

### 許可

-   requested_vehicle未選択行は無視
-   同一車両重複は **現仕様では許可**
    
    -   理由: 別時間・別目的で複数便を申請できるため

* * *

# 9. Query / Prefetch 契約

一覧画面では N+1 を避けること。

## ProductionDetailView の ProcessDay 取得時

最低限以下を prefetch する。

Python

実行する

.prefetch_related(  
    "staff_requests",  
    "staff_requests__position",  
    "vehicle_requests",  
    "vehicle_requests__requested_vehicle",  
)

* * *

# 10. エラーメッセージ方針

## HTMLモーダル

-   `error_message` を context に載せる
-   テンプレート上部に表示する

## JSON API

-   コピー元なしは 200 + 空配列で返す
-   例外は必要に応じて 400 / 500 でもよいが、通常運用では「空」で扱う方が UI は安定する

* * *

# 11. 命名ルール

## View

-   `XxxBulkEditView`
-   `PreviousXxxView`

## URL name

-   `xxx_bulk_edit`
-   `xxx_previous`

## JSON key

-   snake_case
-   datetime/time は文字列化して返す

* * *

# 12. 将来拡張時の契約

将来、管理側配車UIを作る場合も、申請側 Contract は壊さない。

### 申請側

-   ProcessDay単位
-   断片的な希望

### 管理側

-   Performance単位
-   統合・分割・並び替え可能な運行構築

つまり、

Plain text

VehicleRequest != VehicleOperation

は常に維持する。

* * *

# 13. AI実装時の注意

1.  成功時は HX-Redirect を返す
2.  バリデーション失敗時はモーダルHTML再描画
3.  bulk edit は requests_json で統一
4.  JSON返却仕様を勝手に変えない
5.  HTMX target / swap を勝手に変えない
6.  Alpine 再初期化前提を壊さない
7.  Request と Operation を混同しない

* * *

# 14. 最終原則

Plain text

HTML編集はHTMXモーダル  
複数行編集はAlpine + requests_json  
成功時はHX-Redirect  
補助取得はJSON  
申請は断片  
運行は管理側で構築

