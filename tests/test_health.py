def test_health_returns_ok(client):
    # Call the health endpoint
    response = client.get("/health")

    # It should answer 200 with status ok
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
