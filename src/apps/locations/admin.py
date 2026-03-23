import requests
from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path

from apps.locations.models import Location
from apps.locations.services import sync_locations_from_shin_on_db


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["sort", "name", "furigana", "postal_code", "address", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "furigana", "address"]
    ordering = ["sort", "name"]
    change_list_template = "admin/locations/location/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "sync/",
                self.admin_site.admin_view(self.sync_view),
                name="locations_location_sync",
            ),
        ]
        return custom_urls + urls

    def sync_view(self, request):
        context = {
            **self.admin_site.each_context(request),
            "title": "場所マスタ同期（shin-on_db）",
            "opts": self.model._meta,
        }

        if request.method == "POST":
            portal_jwt = request.COOKIES.get("portal_jwt")
            if not portal_jwt:
                context["error"] = (
                    "Portal JWT が見つかりません。再ログインしてください。"
                )
            else:
                try:
                    context["result"] = sync_locations_from_shin_on_db(portal_jwt)
                except requests.HTTPError as e:
                    context["error"] = (
                        f"API エラーが発生しました（{e.response.status_code}）。"
                        "再ログインしてお試しください。"
                    )
                except requests.ConnectionError:
                    context["error"] = (
                        "shin-on_db への接続に失敗しました。ネットワーク設定を確認してください。"
                    )
                except Exception as e:
                    context["error"] = f"同期に失敗しました: {e}"

        return TemplateResponse(request, "admin/locations/location/sync.html", context)
