"""Unit tests for OpenAI web search functionality"""

import json
import os

import pytest

# Set minimal Spotify credentials to allow module import
# (function_app initializes spotify_client at module level)
# Don't set REFRESH_TOKEN to avoid actual Spotify API calls during import
os.environ.setdefault("SPOTIFY_CLIENT_ID", "dummy_client_id")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "dummy_client_secret")

from function_app import openai_web_search


class TestOpenAIWebSearch:
    """Test class for OpenAI web search functionality"""

    def test_openai_web_search_success(self):
        """
        Test successful OpenAI web search with real API call
        """
        # Skip test if API key is not set
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY environment variable not set")

        # Arrange
        mock_context = json.dumps({"arguments": {"query": "What is Python programming?"}})

        # Act
        result = openai_web_search(mock_context)

        # Output API result for pytest -s
        print("\n=== OpenAI Web Search Result ===")
        print(result)
        print("=== End OpenAI Web Search Result ===\n")

        # Assert
        assert result is not None
        assert len(result) > 0
        assert "Python" in result
