from django.http import HttpResponse


def healthcheck(_request):
    """コンテナのHTTP応答だけを確認する軽量ヘルスチェック。"""
    return HttpResponse(status=204)
