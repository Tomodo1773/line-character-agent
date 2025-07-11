"""Unit tests for Spotify search functionality"""

import json
import os

import pytest

from function_app import spotify_search


class TestSpotifySearch:
    """Test class for Spotify search functionality"""

    def test_spotify_search_success(self):
        """
        Test successful Spotify search with real API call
        """
        # Skip test if required Spotify environment variables are not set
        required_vars = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN"]
        for var in required_vars:
            if not os.getenv(var):
                pytest.skip(f"{var} environment variable not set")

        # Arrange
        mock_context = json.dumps({"arguments": {"query": "Beatles", "qtype": "track", "limit": 5}})

        # Act
        result = spotify_search(mock_context)

        # Output API result for pytest -s
        print("\n=== Spotify API Result ===")
        print(result)
        print("=== End Spotify API Result ===\n")

        # Assert
        assert result is not None
        assert len(result) > 0

        # Verify it's valid JSON
        result_dict = json.loads(result)
        assert "tracks" in result_dict
