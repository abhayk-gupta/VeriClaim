import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_session
from app.models.claim import ClaimStatus, ClaimOutcome
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_db_session(mocker):
    session_mock = mocker.AsyncMock()
    app.dependency_overrides[get_session] = lambda: session_mock
    yield session_mock
    app.dependency_overrides.clear()

from app.routers.auth import get_current_agent

def test_list_claims(client, mock_db_session, mocker):
    app.dependency_overrides[get_current_agent] = lambda: mocker.Mock(id="agent123")
    
    mock_result = mocker.Mock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result
    
    response = client.get(
        "/api/v1/claims",
        headers={"Authorization": "Bearer fake_token"}
    )
    
    app.dependency_overrides.pop(get_current_agent, None)
    assert response.status_code == 200

def test_override_claim(client, mock_db_session, mocker):
    app.dependency_overrides[get_current_agent] = lambda: mocker.Mock(id="agent123", email="agent@vericlaim.test")
    mocker.patch("worker.tasks.send_whatsapp.send_text.delay", return_value=None)
    
    from app.models.claim import Claim, ClaimType
    from datetime import datetime
    
    valid_uuid = "12345678-1234-5678-1234-567812345678"
    cust_uuid = "87654321-4321-8765-4321-876543210987"
    ord_uuid = "00000000-0000-0000-0000-000000000000"
    
    real_claim = Claim(
        id=valid_uuid,
        customer_id=cust_uuid,
        order_id=ord_uuid,
        status=ClaimStatus.ESCALATED,
        claim_type=ClaimType.DAMAGED,
        fraud_score=0.0,
        fraud_signals={},
        created_at=datetime.utcnow()
    )
    
    from app.models.customer import Customer
    
    real_customer = Customer(
        id=cust_uuid,
        phone_e164="+1234567890"
    )
    
    async def mock_get(model, obj_id):
        if model == Claim:
            return real_claim
        if model == Customer:
            return real_customer
        return None
        
    mock_db_session.get.side_effect = mock_get
    
    response = client.post(
        f"/api/v1/claims/{valid_uuid}/override",
        headers={"Authorization": "Bearer fake_token"},
        json={
            "outcome": ClaimOutcome.REFUND.value,
            "resolution_notes": "Approved testing refund."
        }
    )
    
    app.dependency_overrides.pop(get_current_agent, None)
    assert response.status_code == 200
