import logging
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


def login_view(request):
    """
    未認証ユーザーを shin•on Portal のログインページへリダイレクトする。

    login_required が ?next=/path/ をセットするのでフルURLに変換してポータルへ渡す。
    ポータルは OTP 完了後にこのURLへリダイレクトする。
    """
    if request.user.is_authenticated:
        return redirect('/')

    next_path = request.GET.get('next', '/')
    # Open Redirect 対策: 外部URLを拒否し、相対パスのみ許可する
    parsed = urlparse(next_path)
    if parsed.scheme or parsed.netloc:
        next_path = '/'

    next_url = request.build_absolute_uri(next_path)
    portal_url = f'{settings.PORTAL_LOGIN_URL}?{urlencode({"next": next_url})}'
    return redirect(portal_url)


def logout_view(request):
    """ログアウトしてログインページへリダイレクトする"""
    if request.method != 'POST':
        return redirect('/')

    logout(request)

    # portal_jwt クッキーを削除して、ミドルウェアによる即時自動ログインを防止する
    response = redirect('accounts:login')
    response.delete_cookie('portal_jwt', path='/')

    logger.info(f'ユーザーがログアウトしました: user={request.user}')
    return response
