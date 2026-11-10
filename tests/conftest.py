import pytest
from src.app import create_app, db


@pytest.fixture
def app():
    """Create and configure a testing Flask application instance."""
    app = create_app("testing")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """A test client for making simulated HTTP requests."""
    return app.test_client()
