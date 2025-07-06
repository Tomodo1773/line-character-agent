"""
Unit tests for Spotify search functionality
"""

import json
from unittest.mock import Mock, patch, MagicMock

import pytest
from spotipy import SpotifyException

from function_app import spotify_search
from spotify_api import Client


class TestSpotifySearch:
    """Test class for Spotify search functionality"""

    def test_spotify_search_success(self):
        """
        Test successful Spotify search
        - Mock Spotify API response
        - Verify correct response format
        - Verify proper query processing
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "Beatles",
                "qtype": "track",
                "limit": 5
            }
        })
        
        mock_search_results = {
            "tracks": [
                {
                    "name": "Hey Jude",
                    "id": "track123",
                    "artists": ["The Beatles"]
                }
            ]
        }
        
        # Act & Assert
        with patch('function_app.spotify_client') as mock_spotify_client:
            mock_spotify_client.search.return_value = mock_search_results
            
            result = spotify_search(mock_context)
            
            # Verify search was called with correct parameters
            mock_spotify_client.search.assert_called_once_with(
                query="Beatles",
                qtype="track",
                limit=5
            )
            
            # Verify result is valid JSON
            result_dict = json.loads(result)
            assert result_dict == mock_search_results

    def test_spotify_search_default_parameters(self):
        """
        Test Spotify search with default parameters
        - Verify default qtype is "track"
        - Verify default limit is 10
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "test song"
            }
        })
        
        mock_search_results = {"tracks": []}
        
        # Act & Assert
        with patch('function_app.spotify_client') as mock_spotify_client:
            mock_spotify_client.search.return_value = mock_search_results
            
            spotify_search(mock_context)
            
            # Verify default parameters were used
            mock_spotify_client.search.assert_called_once_with(
                query="test song",
                qtype="track",
                limit=10
            )

    def test_spotify_search_multiple_types(self):
        """
        Test Spotify search with multiple types
        - Verify searching for multiple types works
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "Beatles",
                "qtype": "track,album,artist",
                "limit": 5
            }
        })
        
        mock_search_results = {
            "tracks": [],
            "albums": [],
            "artists": []
        }
        
        # Act & Assert
        with patch('function_app.spotify_client') as mock_spotify_client:
            mock_spotify_client.search.return_value = mock_search_results
            
            result = spotify_search(mock_context)
            
            # Verify search was called with correct parameters
            mock_spotify_client.search.assert_called_once_with(
                query="Beatles",
                qtype="track,album,artist",
                limit=5
            )
            
            # Verify result contains all types
            result_dict = json.loads(result)
            assert "tracks" in result_dict
            assert "albums" in result_dict
            assert "artists" in result_dict

    def test_spotify_search_spotify_exception(self):
        """
        Test Spotify search with SpotifyException
        - Verify proper error handling for Spotify API errors
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "test"
            }
        })
        
        # Act & Assert
        with patch('function_app.spotify_client') as mock_spotify_client:
            mock_spotify_client.search.side_effect = SpotifyException(
                http_status=401,
                code=-1,
                msg="Unauthorized"
            )
            
            result = spotify_search(mock_context)
            
            assert "An error occurred with the Spotify Client:" in result
            assert "Unauthorized" in result

    def test_spotify_search_general_exception(self):
        """
        Test Spotify search with general exception
        - Verify proper error handling for unexpected errors
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "test"
            }
        })
        
        # Act & Assert
        with patch('function_app.spotify_client') as mock_spotify_client:
            mock_spotify_client.search.side_effect = Exception("Unexpected error")
            
            result = spotify_search(mock_context)
            
            assert result == "An internal server error occurred. Please try again later."

    def test_spotify_search_malformed_context(self):
        """
        Test Spotify search with malformed context
        - Verify error handling for invalid JSON context
        """
        # Arrange
        mock_context = "invalid json"
        
        # Act & Assert
        result = spotify_search(mock_context)
        
        assert result == "An internal server error occurred. Please try again later."

    def test_spotify_search_empty_query(self):
        """
        Test Spotify search with empty query
        - Verify system handles empty query gracefully
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": ""
            }
        })
        
        mock_search_results = {"tracks": []}
        
        # Act & Assert
        with patch('function_app.spotify_client') as mock_spotify_client:
            mock_spotify_client.search.return_value = mock_search_results
            
            result = spotify_search(mock_context)
            
            # Verify empty query was passed to search
            mock_spotify_client.search.assert_called_once_with(
                query="",
                qtype="track",
                limit=10
            )
            
            result_dict = json.loads(result)
            assert result_dict == mock_search_results

    def test_spotify_search_missing_arguments(self):
        """
        Test Spotify search with missing arguments
        - Verify system handles missing arguments gracefully
        """
        # Arrange
        mock_context = json.dumps({})
        
        mock_search_results = {"tracks": []}
        
        # Act & Assert
        with patch('function_app.spotify_client') as mock_spotify_client:
            mock_spotify_client.search.return_value = mock_search_results
            
            result = spotify_search(mock_context)
            
            # Verify default values were used
            mock_spotify_client.search.assert_called_once_with(
                query="",
                qtype="track",
                limit=10
            )


class TestSpotifyClient:
    """Test class for Spotify Client search method"""

    def test_client_search_success(self):
        """
        Test successful Spotify client search
        - Mock spotipy search response
        - Verify correct response parsing
        """
        # Arrange
        mock_logger = Mock()
        mock_token_cache = {"token": {"access_token": "test_token", "expires_at": 9999999999}}
        
        mock_search_results = {
            "tracks": {
                "items": [
                    {
                        "name": "Test Track",
                        "id": "track123",
                        "artists": [{"name": "Test Artist"}],
                        "album": {"name": "Test Album"}
                    }
                ]
            }
        }
        
        # Act & Assert
        with patch('spotify_api.spotipy.Spotify') as mock_spotify:
            with patch('spotify_api.CLIENT_ID', 'test_client_id'):
                with patch('spotify_api.CLIENT_SECRET', 'test_client_secret'):
                    with patch('spotify_api.REFRESH_TOKEN', 'test_refresh_token'):
                        mock_sp_instance = Mock()
                        mock_sp_instance.search.return_value = mock_search_results
                        mock_sp_instance.current_user.return_value = {"display_name": "test_user"}
                        mock_spotify.return_value = mock_sp_instance
                        
                        client = Client(mock_logger, mock_token_cache)
                        
                        with patch.object(client, 'set_username'):
                            with patch('spotify_api.utils.parse_search_results') as mock_parse:
                                mock_parse.return_value = {"tracks": [{"name": "Test Track"}]}
                                
                                result = client.search("test query", "track", 5)
                                
                                # Verify search was called with correct parameters
                                mock_sp_instance.search.assert_called_once_with(
                                    q="test query",
                                    limit=5,
                                    type="track"
                                )
                                
                                # Verify parsing was called
                                mock_parse.assert_called_once_with(
                                    mock_search_results,
                                    "track",
                                    None
                                )
                                
                                assert result == {"tracks": [{"name": "Test Track"}]}

    def test_client_search_no_results(self):
        """
        Test Spotify client search with no results
        - Verify proper error handling when no results are found
        """
        # Arrange
        mock_logger = Mock()
        mock_token_cache = {"token": {"access_token": "test_token", "expires_at": 9999999999}}
        
        # Act & Assert
        with patch('spotify_api.spotipy.Spotify') as mock_spotify:
            with patch('spotify_api.CLIENT_ID', 'test_client_id'):
                with patch('spotify_api.CLIENT_SECRET', 'test_client_secret'):
                    with patch('spotify_api.REFRESH_TOKEN', 'test_refresh_token'):
                        mock_sp_instance = Mock()
                        mock_sp_instance.search.return_value = None
                        mock_sp_instance.current_user.return_value = {"display_name": "test_user"}
                        mock_spotify.return_value = mock_sp_instance
                        
                        client = Client(mock_logger, mock_token_cache)
                        
                        with pytest.raises(ValueError) as exc_info:
                            client.search("test query")
                        
                        assert str(exc_info.value) == "No search results found."

    def test_client_search_with_username_setting(self):
        """
        Test Spotify client search with username setting
        - Verify username is set when it's None
        """
        # Arrange
        mock_logger = Mock()
        mock_token_cache = {"token": {"access_token": "test_token", "expires_at": 9999999999}}
        
        mock_search_results = {
            "tracks": {
                "items": [
                    {
                        "name": "Test Track",
                        "id": "track123",
                        "artists": [{"name": "Test Artist"}],
                        "album": {"name": "Test Album"}
                    }
                ]
            }
        }
        
        # Act & Assert
        with patch('spotify_api.spotipy.Spotify') as mock_spotify:
            with patch('spotify_api.CLIENT_ID', 'test_client_id'):
                with patch('spotify_api.CLIENT_SECRET', 'test_client_secret'):
                    with patch('spotify_api.REFRESH_TOKEN', 'test_refresh_token'):
                        mock_sp_instance = Mock()
                        mock_sp_instance.search.return_value = mock_search_results
                        mock_sp_instance.current_user.return_value = {"display_name": "test_user"}
                        mock_spotify.return_value = mock_sp_instance
                        
                        client = Client(mock_logger, mock_token_cache)
                        client.username = None  # Ensure username is None
                        
                        with patch.object(client, 'set_username') as mock_set_username:
                            with patch('spotify_api.utils.parse_search_results') as mock_parse:
                                mock_parse.return_value = {"tracks": []}
                                
                                client.search("test query")
                                
                                # Verify set_username was called
                                mock_set_username.assert_called_once()