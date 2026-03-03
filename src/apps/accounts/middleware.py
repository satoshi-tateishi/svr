"""
PortalJWTMiddleware

shin•on Portal が発行した portal_jwt クッキー（RS256 署名）を検証し、
認証済みユーザーを Django セッションに紐付けるミドルウェア。

【動作フロー】
1. portal_jwt クッキーを読み取る（なければスキップ）
2. Portal の JWKS エンドポイントから公開鍵を取得して署名を検証
3. JWT の sub（portal_uuid）で UserProfile を検索
4. 見つからなければ email で既存ユーザーを検索し portal_uuid を自動リンク（初回のみ）
5. どちらも見つからなければ JWT ペイロードで新規ユーザーを自動作成
6. ユーザーが確定したら Django セッションにログイン状態を記録

【セキュリティ設計】
- JWT が無効・期限切れの場合はスキップ（既存認証にフォールバック）
- JWKS はライブラリによりメモリキャッシュ（プロセス再起動まで保持）

【設定項目 (settings.py)】
- PORTAL_JWKS_URL  : JWKSエンドポイントURL（例: http://portal-app:8000/api/jwks/）
- PORTAL_JWT_ISSUER: JWT の iss クレームと照合する発行者
- PORTAL_JWT_AUDIENCE: JWT の aud クレームと照合する対象

【ハマりポイント】
新規ユーザー作成後は必ず user.profile（キャッシュ経由）でアクセスすること。
get_or_create 経由だと login() 発火の post_save シグナルで portal_uuid が上書きされる。
詳細: rf_finder/docs/01_APP_INTEGRATION_GUIDE.md「Django post_save シグナルとの干渉バグ」参照。
"""

import logging

import jwt
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from jwt import PyJWKClient

logger = logging.getLogger(__name__)


class PortalJWTMiddleware:
    """
    portal_jwt クッキーを検証し、認証済みユーザーを Django セッションに紐付ける。
    """

    # プロセス全体で JWKS クライアントを共有（クラス変数でキャッシュ）
    _jwks_client: PyJWKClient | None = None

    def __init__(self, get_response):
        self.get_response = get_response
        # JWKS クライアントを初期化（cache_keys=True でメモリキャッシュ有効）
        if PortalJWTMiddleware._jwks_client is None:
            PortalJWTMiddleware._jwks_client = PyJWKClient(settings.PORTAL_JWKS_URL, cache_keys=True)

    def __call__(self, request):
        # AuthenticationMiddleware が設定した request.user を確認し、
        # 未認証のときのみ JWT 認証を試みる
        if not request.user.is_authenticated:
            self._authenticate_with_jwt(request)
        return self.get_response(request)

    def _authenticate_with_jwt(self, request):
        """portal_jwt クッキーを検証してユーザーを認証する"""
        portal_jwt_token = request.COOKIES.get('portal_jwt')
        if not portal_jwt_token:
            return

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(portal_jwt_token)
            payload = jwt.decode(
                portal_jwt_token,
                signing_key.key,
                algorithms=['RS256'],
                audience=settings.PORTAL_JWT_AUDIENCE,
                issuer=settings.PORTAL_JWT_ISSUER,
            )
        except jwt.ExpiredSignatureError:
            logger.info('portal_jwt が期限切れです。再認証が必要です。')
            return
        except jwt.InvalidTokenError as e:
            logger.warning(f'portal_jwt の検証に失敗しました: {e}')
            return
        except Exception as e:
            logger.error(f'portal_jwt 処理中に予期しないエラー: {e}', exc_info=True)
            return

        portal_uuid = payload.get('sub')
        email = payload.get('email', '')

        if not portal_uuid:
            logger.warning('portal_jwt に sub クレームがありません')
            return

        user = self._get_or_link_user(portal_uuid, email, payload)
        if user is None:
            logger.info(f'portal_uuid={portal_uuid} に対応するユーザーが見つかりません。アクセスを拒否します。')
            return

        if not user.is_active:
            logger.info(f'非アクティブユーザーのアクセスを拒否しました: {user.email}')
            return

        # Django セッションにログイン状態を記録（以降のリクエストはセッションを利用）
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        logger.debug(f'JWT 認証成功: {user.email} (portal_uuid={portal_uuid})')

    def _get_or_link_user(self, portal_uuid: str, email: str, payload: dict) -> User | None:
        """
        portal_uuid でユーザーを検索する。

        見つからなければ email で既存ユーザーを検索して portal_uuid を自動リンクする（初回のみ）。
        email でも見つからなければ JWT ペイロードの情報で新規ユーザーを自動作成する。
        """
        from .models import UserProfile

        # 1. portal_uuid で既存の紐付けを検索（最速）
        try:
            profile = UserProfile.objects.select_related('user').get(portal_uuid=portal_uuid)
            # JWT に含まれる電話番号を常に最新値で同期する
            jwt_phone = payload.get('phone_number', '')
            if jwt_phone and profile.phone_number != jwt_phone:
                profile.phone_number = jwt_phone
                profile.save(update_fields=['phone_number'])
            return profile.user
        except UserProfile.DoesNotExist:
            pass

        # 2. 初回ログイン: email で既存ユーザーを検索して portal_uuid を紐付け
        if not email:
            return None

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # 3. 新規ユーザーを自動作成（ポータル経由の初回アクセス）
            user = User.objects.create_user(
                username=portal_uuid,
                email=email,
                password=None,
            )
            # user.profile を経由してキャッシュを更新する。
            # get_or_create だとキャッシュが更新されず、login() 後の
            # update_last_login → post_save → save_user_profile で
            # 古いキャッシュ（portal_uuid=None）に上書きされてしまう。
            profile = user.profile
            profile.portal_uuid = portal_uuid
            profile.family_name = payload.get('family_name', '')
            profile.given_name = payload.get('given_name', '')
            profile.phonetic_family_name = payload.get('phonetic_family_name', '')
            profile.phonetic_given_name = payload.get('phonetic_given_name', '')
            profile.phone_number = payload.get('phone_number', '')
            profile.email = email
            profile.save()
            logger.info(f'新規ユーザーを自動作成しました: {email} (portal_uuid={portal_uuid})')
            return user
        except User.MultipleObjectsReturned:
            logger.warning(f'email={email} のユーザーが複数存在します。最初の1件を使用します。')
            user = User.objects.filter(email=email).order_by('id').first()

        # UserProfile に portal_uuid を保存（以降は portal_uuid で高速検索）
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.portal_uuid = portal_uuid
        # JWT から最新のプロフィール情報を同期（既存値がない場合のみ上書き）
        if not profile.family_name:
            profile.family_name = payload.get('family_name', '')
        if not profile.given_name:
            profile.given_name = payload.get('given_name', '')
        if not profile.phonetic_family_name:
            profile.phonetic_family_name = payload.get('phonetic_family_name', '')
        if not profile.phonetic_given_name:
            profile.phonetic_given_name = payload.get('phonetic_given_name', '')
        if not profile.phone_number:
            profile.phone_number = payload.get('phone_number', '')
        if not profile.email:
            profile.email = email
        profile.save()

        logger.info(f'portal_uuid を自動リンクしました: {user.email} -> portal_uuid={portal_uuid}')
        return user
