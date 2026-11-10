def test_health_check_endpoint(client):
    """Test that the /health endpoint responds with 200 OK and valid health metrics."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "healthy"
    assert "timestamp" in data
    assert "python_version" in data
    assert "storage_backend" in data


def test_index_page(client):
    """Test that the index landing page loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"OpenInvite" in response.data
    assert b"Self-Hosted Event Invitation" in response.data
