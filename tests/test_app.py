import pytest
import re
from app import create_app

@pytest.fixture
def client():
    # Create a test version of our app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_pages_return_200(client):
    """Test that Classifier, About, Guide, and Analytics pages load successfully."""
    assert client.get('/').status_code == 200
    assert client.get('/about').status_code == 200
    assert client.get('/guide').status_code == 200
    # Uncomment this once you build the analytics page
    # assert client.get('/analytics').status_code == 200

def test_404_page(client):
    """Test that unknown URLs return the custom 404 page."""
    response = client.get('/this-page-does-not-exist')
    assert response.status_code == 404
    assert b"Page Not Found" in response.data

def test_security_headers(client):
    """Test that security headers are present on every request."""
    response = client.get('/about')
    assert 'Content-Security-Policy' in response.headers
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'

def test_api_empty_input(client):
    """Test that the API rejects empty text."""
    response = client.post('/classify', json={"description": ""})
    assert response.status_code == 400
    assert b"Description cannot be empty" in response.data

def test_api_too_long(client):
    """Test that the API rejects text over 500 characters."""
    long_text = "a" * 501
    response = client.post('/classify', json={"description": long_text})
    assert response.status_code == 400
    assert b"Description exceeds 500 characters" in response.data

def test_api_valid_input(client):
    """Test that a valid description returns a structured JSON payload."""
    response = client.post('/classify', json={"description": "stainless steel kitchen sink"})
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert 'predicted_code' in data
    assert 'bands_out' in data
    assert 'retrieval' in data

def test_batch_api(client):
    """Test the batch endpoint."""
    response = client.post('/classify-batch', json={"descriptions": ["laptop", "fresh mango"]})
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['results']) == 2
    # Laptop should be OK
    assert data['results'][0]['status'] == 'ok'
    # Mango should be out of scope (triggered by the pipeline)
    assert data['results'][1]['status'] == 'ok' 
    assert data['results'][1]['data']['status'] == 'out_of_scope'