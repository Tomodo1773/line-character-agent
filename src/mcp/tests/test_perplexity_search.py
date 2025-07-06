"""
Unit tests for Perplexity web search functionality
"""

import json
import os
from unittest.mock import Mock, patch

import pytest

from function_app import perplexity_web_search


class TestPerplexityWebSearch:
    """Test class for Perplexity web search functionality"""

    def test_perplexity_web_search_success(self):
        """
        Test successful Perplexity web search
        - Mock OpenAI API response
        - Verify correct response format
        - Verify proper query processing
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "Python programming basics"
            }
        })
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Python is a programming language..."
        
        # Act & Assert
        with patch('function_app.OpenAI') as mock_openai_class:
            with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'test_key'}):
                mock_client = Mock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai_class.return_value = mock_client
                
                result = perplexity_web_search(mock_context)
                
                # Verify OpenAI client was initialized correctly
                mock_openai_class.assert_called_once_with(
                    api_key='test_key',
                    base_url='https://api.perplexity.ai'
                )
                
                # Verify completion was called with correct parameters
                mock_client.chat.completions.create.assert_called_once()
                call_args = mock_client.chat.completions.create.call_args
                
                assert call_args[1]['model'] == 'sonar'
                assert len(call_args[1]['messages']) == 2
                assert call_args[1]['messages'][0]['role'] == 'system'
                assert call_args[1]['messages'][1]['role'] == 'user'
                assert call_args[1]['messages'][1]['content'] == 'Python programming basics'
                
                # Verify result
                assert result == "Python is a programming language..."

    def test_perplexity_web_search_missing_api_key(self):
        """
        Test Perplexity web search with missing API key
        - Verify error message is returned when API key is not set
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "test query"
            }
        })
        
        # Act & Assert
        with patch.dict(os.environ, {}, clear=True):
            result = perplexity_web_search(mock_context)
            
            assert result == "PERPLEXITY_API_KEYが環境変数にセットされていません。APIキーをセットしてから利用してください。"

    def test_perplexity_web_search_empty_query(self):
        """
        Test Perplexity web search with empty query
        - Verify system handles empty query gracefully
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": ""
            }
        })
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Please provide a query"
        
        # Act & Assert
        with patch('function_app.OpenAI') as mock_openai_class:
            with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'test_key'}):
                mock_client = Mock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai_class.return_value = mock_client
                
                result = perplexity_web_search(mock_context)
                
                # Verify empty query was passed to API
                call_args = mock_client.chat.completions.create.call_args
                assert call_args[1]['messages'][1]['content'] == ""
                
                assert result == "Please provide a query"

    def test_perplexity_web_search_api_error(self):
        """
        Test Perplexity web search with API error
        - Verify error handling when API call fails
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "test query"
            }
        })
        
        # Act & Assert
        with patch('function_app.OpenAI') as mock_openai_class:
            with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'test_key'}):
                mock_client = Mock()
                mock_client.chat.completions.create.side_effect = Exception("API Error")
                mock_openai_class.return_value = mock_client
                
                result = perplexity_web_search(mock_context)
                
                assert "Perplexity Web検索でエラーが発生しました: API Error" in result

    def test_perplexity_web_search_malformed_context(self):
        """
        Test Perplexity web search with malformed context
        - Verify error handling for invalid JSON context
        """
        # Arrange
        mock_context = "invalid json"
        
        # Act & Assert
        with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'test_key'}):
            result = perplexity_web_search(mock_context)
            
            assert "Perplexity Web検索でエラーが発生しました:" in result

    def test_perplexity_web_search_missing_arguments(self):
        """
        Test Perplexity web search with missing arguments
        - Verify system handles missing arguments gracefully
        """
        # Arrange
        mock_context = json.dumps({})
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "No query provided"
        
        # Act & Assert
        with patch('function_app.OpenAI') as mock_openai_class:
            with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'test_key'}):
                mock_client = Mock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai_class.return_value = mock_client
                
                result = perplexity_web_search(mock_context)
                
                # Verify empty query was passed when arguments are missing
                call_args = mock_client.chat.completions.create.call_args
                assert call_args[1]['messages'][1]['content'] == ""
                
                assert result == "No query provided"

    def test_perplexity_web_search_system_message(self):
        """
        Test that system message is properly set
        - Verify system message contains correct instructions
        """
        # Arrange
        mock_context = json.dumps({
            "arguments": {
                "query": "test query"
            }
        })
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "test response"
        
        # Act & Assert
        with patch('function_app.OpenAI') as mock_openai_class:
            with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'test_key'}):
                mock_client = Mock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai_class.return_value = mock_client
                
                perplexity_web_search(mock_context)
                
                # Verify system message content
                call_args = mock_client.chat.completions.create.call_args
                system_message = call_args[1]['messages'][0]['content']
                
                assert "You are a helpful AI assistant" in system_message
                assert "Provide only the final answer" in system_message
                assert "Do not show the intermediate steps" in system_message