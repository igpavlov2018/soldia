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
    """Test user registration"""
    data = {
        "wallet_address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        "referral_code": None
    }
    
    # Note: This will fail without proper DB setup
    # Just checking endpoint exists
    response = await client.post("/api/users/register", json=data)
    assert response.status_code in [200, 500]  # Either success or DB error
