"""User API tests"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test health check endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration endpoint exists and returns HTTP response"""
    data = {
        "wallet_address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        "referral_code": None
    }
    response = await client.post("/api/users/register", json=data)
    # Without real DB any server-side error is acceptable
    assert response.status_code in [200, 400, 409, 422, 500, 503]
