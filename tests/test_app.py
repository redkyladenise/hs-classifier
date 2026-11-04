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
    """Test that About and guide pages load successfully."""
    assert client.get('/about').status_code == 200
    assert client.get('/guide').status_code == 200

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

def test_disclaimer_and_tariff_finder(client):
    """Test that the disclaimer and Tariff Finder link are on both pages."""
    for page in ['/about', '/guide']:
        response = client.get(page)
        assert b"Assistive tool, not an official classification." in response.data
        assert b"https://finder.tariffcommission.gov.ph/" in response.data

def test_exactly_one_h1(client):
    """Test that each page has exactly one main H1 heading."""
    for page in ['/about', '/guide']:
        response = client.get(page)
        # Use regex to count how many <h1> tags exist
        h1_count = len(re.findall(rb'<h1\b', response.data))
        assert h1_count == 1, f"Expected 1 h1 on {page}, found {h1_count}"