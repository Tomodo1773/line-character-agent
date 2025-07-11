"""Unit tests for Perplexity web search functionality"""

import json
import os

import pytest

from function_app import perplexity_web_search


class TestPerplexityWebSearch:
    """Test class for Perplexity web search functionality"""

    def test_perplexity_web_search_success(self):
        """
        Test successful Perplexity web search with real API call
        """
        # Skip test if API key is not set
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            pytest.skip("PERPLEXITY_API_KEY environment variable not set")

        # Arrange
        mock_context = json.dumps({"arguments": {"query": "What is Python programming?"}})

        # Act
        result = perplexity_web_search(mock_context)

        # Output API result for pytest -s
        print("\n=== Perplexity API Result ===")
        print(result)
        print("=== End Perplexity API Result ===\n")

        # Assert
        assert result is not None
        assert len(result) > 0
        assert "Python" in result
