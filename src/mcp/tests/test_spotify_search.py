"""Unit tests for Spotify search functionality"""

import json
import os

import pytest

from function_app import spotify_search, spotify_search_my_playlists


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

    def test_spotify_search_my_playlists_success(self):
        """
        Test successful Spotify search my playlists with real API call
        """
        # Skip test if required Spotify environment variables are not set
        required_vars = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN"]
        for var in required_vars:
            if not os.getenv(var):
                pytest.skip(f"{var} environment variable not set")

        # Arrange
        mock_context = json.dumps({"arguments": {"query": "test", "limit": 10}})

        # Act
        result = spotify_search_my_playlists(mock_context)

        # Output API result for pytest -s
        print("\n=== Spotify Search My Playlists API Result ===")
        print(result)
        print("=== End Spotify Search My Playlists API Result ===\n")

        # Assert
        assert result is not None
        assert len(result) > 0

        # JSONレスポンスの場合は検証
        if result.startswith("{"):
            result_dict = json.loads(result)
            assert "playlists" in result_dict

    def test_spotify_search_my_playlists_not_found(self):
        """
        Test Spotify search my playlists with a query that should not match any playlist
        """
        # Skip test if required Spotify environment variables are not set
        required_vars = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN"]
        for var in required_vars:
            if not os.getenv(var):
                pytest.skip(f"{var} environment variable not set")

        # Arrange - 存在しないプレイリスト名を検索
        mock_context = json.dumps({"arguments": {"query": "xyz_nonexistent_playlist_name_123", "limit": 10}})

        # Act
        result = spotify_search_my_playlists(mock_context)

        # Output API result for pytest -s
        print("\n=== Spotify Search My Playlists Not Found Result ===")
        print(result)
        print("=== End Spotify Search My Playlists Not Found Result ===\n")

        # Assert
        assert result is not None
        assert "一致するプレイリストが見つかりませんでした" in result
