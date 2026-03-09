from django.http import HttpResponse, HttpResponseForbidden


def permission_denied_response(request, message: str = '権限がありません。') -> HttpResponse:
    if request.headers.get('HX-Request') == 'true':
        html = (
            '<div class="p-4 text-red-600 bg-red-50 rounded border border-red-200">'
            '<p class="font-semibold">権限エラー</p>'
            f'<p class="text-sm">{message}</p>'
            '</div>'
        )
        return HttpResponse(html, status=403)
    return HttpResponseForbidden(message)
