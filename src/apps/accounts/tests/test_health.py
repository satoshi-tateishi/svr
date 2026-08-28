from django.urls import reverse


def test_未認証でヘルスチェックへアクセスできる(client):
    response = client.get(reverse('healthcheck'))

    assert response.status_code == 204
    assert response.content == b''
