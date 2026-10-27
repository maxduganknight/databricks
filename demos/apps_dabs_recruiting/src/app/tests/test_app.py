"""
Smoke tests for the recruiter chatbot app.
Uses Streamlit's AppTest to verify the app loads without errors.
"""

from unittest.mock import patch, MagicMock
from streamlit.testing.v1 import AppTest


@patch("app.WorkspaceClient")
@patch("app.OpenAI")
def test_app_loads_without_error(mock_openai, mock_ws):
    """App should render the main UI elements without throwing."""
    mock_ws.return_value.config.host = "https://test.cloud.databricks.com"
    mock_ws.return_value.config.token = "test-token"

    at = AppTest.from_file("app.py", default_timeout=10)
    at.run()

    assert not at.exception
    assert any("Recruiter Assistant" in el.value for el in at.title)
