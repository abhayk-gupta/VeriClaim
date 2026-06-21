import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_whatsapp_webhook_inbound_image(client, mocker):
    mocker.patch("app.routers.whatsapp._dispatch", return_value=None)
    # Simulate a Twilio/WhatsApp webhook payload
    payload = {
        "From": "whatsapp:+15555551234",
        "Body": "My screen is broken",
        "NumMedia": "1",
        "MediaUrl0": "https://example.com/fake-media-url.jpg"
    }

    response = client.post(
        "/webhooks/whatsapp",
        data=payload
    )

    assert response.status_code == 200
