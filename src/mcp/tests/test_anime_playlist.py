"""Unit tests for anime playlist functionality"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from function_app import get_current_anime_playlist, get_current_season_anime_playlist_name


class TestGetCurrentSeasonAnimePlaylistName:
    """Test class for get_current_season_anime_playlist_name function"""

    @pytest.mark.parametrize(
        "month,expected_season",
        [
            (1, "冬"),
            (2, "冬"),
            (3, "冬"),
            (4, "春"),
            (5, "春"),
            (6, "春"),
            (7, "夏"),
            (8, "夏"),
            (9, "夏"),
            (10, "秋"),
            (11, "秋"),
            (12, "秋"),
        ],
    )
    def test_season_mapping(self, month, expected_season):
        """Test that each month maps to the correct season"""
        jst = timezone(timedelta(hours=9))
        mock_datetime = datetime(2025, month, 15, 12, 0, 0, tzinfo=jst)

        with patch("function_app.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            result = get_current_season_anime_playlist_name()
            assert result == f"2025{expected_season}アニメ"

    def test_returns_string(self):
        """Test that the function returns a string"""
        result = get_current_season_anime_playlist_name()
        assert isinstance(result, str)

    def test_format_matches_expected_pattern(self):
        """Test that the result matches the expected format (YYYY季節アニメ)"""
        result = get_current_season_anime_playlist_name()
        # Should be 4 digits + season + アニメ
        assert len(result) >= 7  # e.g., "2025冬アニメ"
        assert result.endswith("アニメ")
        assert result[:4].isdigit()


class TestGetCurrentAnimePlaylistMcpTool:
    """Test class for get_current_anime_playlist MCP tool"""

    def test_returns_valid_json(self):
        """Test that the MCP tool returns valid JSON"""
        mock_context = json.dumps({"arguments": {}})
        result = get_current_anime_playlist(mock_context)

        # Verify it's valid JSON
        result_dict = json.loads(result)
        assert "playlist_name" in result_dict

    def test_playlist_name_format(self):
        """Test that the returned playlist name has the expected format"""
        mock_context = json.dumps({"arguments": {}})
        result = get_current_anime_playlist(mock_context)

        result_dict = json.loads(result)
        playlist_name = result_dict["playlist_name"]

        assert playlist_name.endswith("アニメ")
        assert playlist_name[:4].isdigit()
        assert any(season in playlist_name for season in ["冬", "春", "夏", "秋"])
