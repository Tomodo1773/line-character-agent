import json
import logging
import sys
from typing import Optional
import urllib.parse

import azure.functions as func
from spotipy import SpotifyException

from spotify_api import Client

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# In-memory token storage (simple approach for demo)
_access_token_cache = {}

def setup_logger():
    class Logger:
        def info(self, message):
            logging.info(message)

        def error(self, message):
            logging.error(message)

    return Logger()


logger = setup_logger()
spotify_client = Client(logger, _access_token_cache)


class ToolProperty:
    def __init__(self, property_name: str, property_type: str, description: str):
        self.propertyName = property_name
        self.propertyType = property_type
        self.description = description

    def to_dict(self):
        return {
            "propertyName": self.propertyName,
            "propertyType": self.propertyType,
            "description": self.description,
        }


# Define tool properties for each MCP tool
playback_properties = [
    ToolProperty("action", "string", "Action to perform: 'get', 'start', 'pause' or 'skip'"),
    ToolProperty("spotify_uri", "string", "Spotify URI of item to play for 'start' action (optional)"),
    ToolProperty("num_skips", "number", "Number of tracks to skip for 'skip' action (default: 1)"),
]

search_properties = [
    ToolProperty("query", "string", "Search query term"),
    ToolProperty("qtype", "string", "Type of items to search for (track, album, artist, playlist, or comma-separated combination) (default: track)"),
    ToolProperty("limit", "number", "Maximum number of items to return (default: 10)"),
]

queue_properties = [
    ToolProperty("action", "string", "Action to perform: 'add' or 'get'"),
    ToolProperty("track_id", "string", "Track ID to add to queue (required for add action)"),
]

get_info_properties = [
    ToolProperty("item_uri", "string", "URI of the item to get information about"),
]

create_playlist_properties = [
    ToolProperty("name", "string", "Name of the playlist to create"),
    ToolProperty("public", "boolean", "Whether the playlist should be public (default: false)"),
    ToolProperty("description", "string", "Description for the playlist (optional)"),
]

add_tracks_to_playlist_properties = [
    ToolProperty("playlist_id", "string", "ID of the playlist to add tracks to"),
    ToolProperty("track_ids", "array", "List of track IDs to add (up to 100)"),
    ToolProperty("position", "number", "Position to insert tracks (optional, default is end)"),
]

add_track_to_liked_songs_properties = [
    ToolProperty("track_id", "string", "ID of the track to add to liked songs"),
]

# Convert tool properties to JSON
playback_properties_json = json.dumps([prop.to_dict() for prop in playback_properties])
search_properties_json = json.dumps([prop.to_dict() for prop in search_properties])
queue_properties_json = json.dumps([prop.to_dict() for prop in queue_properties])
get_info_properties_json = json.dumps([prop.to_dict() for prop in get_info_properties])
create_playlist_properties_json = json.dumps([prop.to_dict() for prop in create_playlist_properties])
add_tracks_to_playlist_properties_json = json.dumps([prop.to_dict() for prop in add_tracks_to_playlist_properties])
add_track_to_liked_songs_properties_json = json.dumps([prop.to_dict() for prop in add_track_to_liked_songs_properties])


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_playback",
    description="Manages the current playback with actions: get (current track info), start (play new item or resume), pause, skip",
    toolProperties=playback_properties_json,
)
def spotify_playback(context) -> str:
    """Handle Spotify playback control."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        action = arguments.get("action")
        
        logger.info(f"Spotify playback called with action: {action}")
        
        match action:
            case "get":
                logger.info("Attempting to get current track")
                curr_track = spotify_client.get_current_track()
                if curr_track:
                    logger.info(f"Current track retrieved: {curr_track.get('name', 'Unknown')}")
                    return json.dumps(curr_track, indent=2)
                logger.info("No track currently playing")
                return "No track playing."
                
            case "start":
                logger.info(f"Starting playback with arguments: {arguments}")
                spotify_client.start_playback(spotify_uri=arguments.get("spotify_uri"))
                logger.info("Playback started successfully")
                return "Playback starting."
                
            case "pause":
                logger.info("Attempting to pause playback")
                spotify_client.pause_playback()
                logger.info("Playback paused successfully")
                return "Playback paused."
                
            case "skip":
                num_skips = int(arguments.get("num_skips", 1))
                logger.info(f"Skipping {num_skips} tracks.")
                spotify_client.skip_track(n=num_skips)
                return "Skipped to next track."
                
            case _:
                return f"Unknown playback action: {action}. Supported actions are: get, start, pause, skip."
                
    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"An error occurred with the Spotify Client: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "An internal server error occurred. Please try again later."


@app.route(route="spotify_auth", auth_level=func.AuthLevel.ANONYMOUS)
def spotify_auth(req: func.HttpRequest) -> func.HttpResponse:
    """Handle Spotify OAuth authentication flow."""
    try:
        # Check if this is a callback with authorization code
        code = req.params.get('code')
        error = req.params.get('error')
        
        if error:
            logger.error(f"OAuth error: {error}")
            return func.HttpResponse(
                f"認証エラー: {error}",
                status_code=400,
                mimetype="text/html; charset=utf-8"
            )
        
        if code:
            # Handle callback - exchange code for token
            try:
                logger.info("Handling OAuth callback with authorization code")
                token_info = spotify_client.auth_manager.get_access_token(code)
                
                # Store token in memory cache
                _access_token_cache['token'] = token_info
                logger.info("OAuth token successfully stored in memory cache")
                
                return func.HttpResponse(
                    """
                    <html>
                    <body>
                        <h2>Spotify認証完了！</h2>
                        <p>認証が正常に完了しました。このウィンドウを閉じてください。</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                    """,
                    status_code=200,
                    mimetype="text/html; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"Error exchanging authorization code: {str(e)}")
                return func.HttpResponse(
                    f"トークン交換エラー: {str(e)}",
                    status_code=400,
                    mimetype="text/html; charset=utf-8"
                )
        else:
            # Generate authorization URL
            logger.info("Generating Spotify authorization URL")
            auth_url = spotify_client.auth_manager.get_authorize_url()
            
            return func.HttpResponse(
                f"""
                <html>
                <body>
                    <h2>Spotify認証</h2>
                    <p>以下のリンクをクリックしてSpotifyにログインしてください：</p>
                    <a href="{auth_url}" target="_blank">Spotifyで認証</a>
                    <p>認証後、自動的にリダイレクトされます。</p>
                </body>
                </html>
                """,
                status_code=200,
                mimetype="text/html; charset=utf-8"
            )
    except Exception as e:
        logger.error(f"Unexpected error in spotify_auth: {str(e)}")
        return func.HttpResponse(
            "認証処理でエラーが発生しました。",
            status_code=500,
            mimetype="text/html; charset=utf-8"
        )


@app.route(route="spotify_auth_status", auth_level=func.AuthLevel.FUNCTION)
def spotify_auth_status(req: func.HttpRequest) -> func.HttpResponse:
    """Check Spotify authentication status."""
    try:
        is_authenticated = spotify_client.auth_ok()
        logger.info(f"Auth status check: {is_authenticated}")
        
        return func.HttpResponse(
            json.dumps({
                "authenticated": is_authenticated,
                "auth_url": f"{req.url.replace('/spotify_auth_status', '/spotify_auth')}" if not is_authenticated else None
            }),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logger.error(f"Error checking auth status: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": "認証状態の確認でエラーが発生しました"}),
            status_code=500,
            mimetype="application/json"
        )


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_search",
    description="Search for tracks, albums, artists, or playlists on Spotify",
    toolProperties=search_properties_json,
)
def spotify_search(context) -> str:
    """Handle Spotify search."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        
        logger.info(f"Performing search with arguments: {arguments}")
        search_results = spotify_client.search(
            query=arguments.get("query", ""),
            qtype=arguments.get("qtype", "track"),
            limit=arguments.get("limit", 10)
        )
        logger.info("Search completed successfully.")
        return json.dumps(search_results, indent=2)
        
    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"An error occurred with the Spotify Client: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "An internal server error occurred. Please try again later."


@app.route(route="spotify_auth", auth_level=func.AuthLevel.ANONYMOUS)
def spotify_auth(req: func.HttpRequest) -> func.HttpResponse:
    """Handle Spotify OAuth authentication flow."""
    try:
        # Check if this is a callback with authorization code
        code = req.params.get('code')
        error = req.params.get('error')
        
        if error:
            logger.error(f"OAuth error: {error}")
            return func.HttpResponse(
                f"認証エラー: {error}",
                status_code=400,
                mimetype="text/html; charset=utf-8"
            )
        
        if code:
            # Handle callback - exchange code for token
            try:
                logger.info("Handling OAuth callback with authorization code")
                token_info = spotify_client.auth_manager.get_access_token(code)
                
                # Store token in memory cache
                _access_token_cache['token'] = token_info
                logger.info("OAuth token successfully stored in memory cache")
                
                return func.HttpResponse(
                    """
                    <html>
                    <body>
                        <h2>Spotify認証完了！</h2>
                        <p>認証が正常に完了しました。このウィンドウを閉じてください。</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                    """,
                    status_code=200,
                    mimetype="text/html; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"Error exchanging authorization code: {str(e)}")
                return func.HttpResponse(
                    f"トークン交換エラー: {str(e)}",
                    status_code=400,
                    mimetype="text/html; charset=utf-8"
                )
        else:
            # Generate authorization URL
            logger.info("Generating Spotify authorization URL")
            auth_url = spotify_client.auth_manager.get_authorize_url()
            
            return func.HttpResponse(
                f"""
                <html>
                <body>
                    <h2>Spotify認証</h2>
                    <p>以下のリンクをクリックしてSpotifyにログインしてください：</p>
                    <a href="{auth_url}" target="_blank">Spotifyで認証</a>
                    <p>認証後、自動的にリダイレクトされます。</p>
                </body>
                </html>
                """,
                status_code=200,
                mimetype="text/html; charset=utf-8"
            )
    except Exception as e:
        logger.error(f"Unexpected error in spotify_auth: {str(e)}")
        return func.HttpResponse(
            "認証処理でエラーが発生しました。",
            status_code=500,
            mimetype="text/html; charset=utf-8"
        )


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_queue",
    description="Manage the playback queue - get the queue or add tracks",
    toolProperties=queue_properties_json,
)
def spotify_queue(context) -> str:
    """Handle Spotify queue management."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        action = arguments.get("action")
        
        logger.info(f"Queue operation with arguments: {arguments}")
        
        match action:
            case "add":
                track_id = arguments.get("track_id")
                if not track_id:
                    logger.error("track_id is required for add to queue.")
                    return "track_id is required for add action"
                spotify_client.add_to_queue(track_id)
                return "Track added to queue."
                
            case "get":
                queue = spotify_client.get_queue()
                return json.dumps(queue, indent=2)
                
            case _:
                return f"Unknown queue action: {action}. Supported actions are: add, get."
                
    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"An error occurred with the Spotify Client: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "An internal server error occurred. Please try again later."


@app.route(route="spotify_auth", auth_level=func.AuthLevel.ANONYMOUS)
def spotify_auth(req: func.HttpRequest) -> func.HttpResponse:
    """Handle Spotify OAuth authentication flow."""
    try:
        # Check if this is a callback with authorization code
        code = req.params.get('code')
        error = req.params.get('error')
        
        if error:
            logger.error(f"OAuth error: {error}")
            return func.HttpResponse(
                f"認証エラー: {error}",
                status_code=400,
                mimetype="text/html; charset=utf-8"
            )
        
        if code:
            # Handle callback - exchange code for token
            try:
                logger.info("Handling OAuth callback with authorization code")
                token_info = spotify_client.auth_manager.get_access_token(code)
                
                # Store token in memory cache
                _access_token_cache['token'] = token_info
                logger.info("OAuth token successfully stored in memory cache")
                
                return func.HttpResponse(
                    """
                    <html>
                    <body>
                        <h2>Spotify認証完了！</h2>
                        <p>認証が正常に完了しました。このウィンドウを閉じてください。</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                    """,
                    status_code=200,
                    mimetype="text/html; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"Error exchanging authorization code: {str(e)}")
                return func.HttpResponse(
                    f"トークン交換エラー: {str(e)}",
                    status_code=400,
                    mimetype="text/html; charset=utf-8"
                )
        else:
            # Generate authorization URL
            logger.info("Generating Spotify authorization URL")
            auth_url = spotify_client.auth_manager.get_authorize_url()
            
            return func.HttpResponse(
                f"""
                <html>
                <body>
                    <h2>Spotify認証</h2>
                    <p>以下のリンクをクリックしてSpotifyにログインしてください：</p>
                    <a href="{auth_url}" target="_blank">Spotifyで認証</a>
                    <p>認証後、自動的にリダイレクトされます。</p>
                </body>
                </html>
                """,
                status_code=200,
                mimetype="text/html; charset=utf-8"
            )
    except Exception as e:
        logger.error(f"Unexpected error in spotify_auth: {str(e)}")
        return func.HttpResponse(
            "認証処理でエラーが発生しました。",
            status_code=500,
            mimetype="text/html; charset=utf-8"
        )


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_get_info",
    description="Get detailed information about a Spotify item (track, album, artist, or playlist)",
    toolProperties=get_info_properties_json,
)
def spotify_get_info(context) -> str:
    """Handle getting detailed Spotify item information."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        
        logger.info(f"Getting item info with arguments: {arguments}")
        item_info = spotify_client.get_info(item_uri=arguments.get("item_uri"))
        return json.dumps(item_info, indent=2)
        
    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"An error occurred with the Spotify Client: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "An internal server error occurred. Please try again later."


@app.route(route="spotify_auth", auth_level=func.AuthLevel.ANONYMOUS)
def spotify_auth(req: func.HttpRequest) -> func.HttpResponse:
    """Handle Spotify OAuth authentication flow."""
    try:
        # Check if this is a callback with authorization code
        code = req.params.get('code')
        error = req.params.get('error')
        
        if error:
            logger.error(f"OAuth error: {error}")
            return func.HttpResponse(
                f"認証エラー: {error}",
                status_code=400,
                mimetype="text/html; charset=utf-8"
            )
        
        if code:
            # Handle callback - exchange code for token
            try:
                logger.info("Handling OAuth callback with authorization code")
                token_info = spotify_client.auth_manager.get_access_token(code)
                
                # Store token in memory cache
                _access_token_cache['token'] = token_info
                logger.info("OAuth token successfully stored in memory cache")
                
                return func.HttpResponse(
                    """
                    <html>
                    <body>
                        <h2>Spotify認証完了！</h2>
                        <p>認証が正常に完了しました。このウィンドウを閉じてください。</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                    """,
                    status_code=200,
                    mimetype="text/html; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"Error exchanging authorization code: {str(e)}")
                return func.HttpResponse(
                    f"トークン交換エラー: {str(e)}",
                    status_code=400,
                    mimetype="text/html; charset=utf-8"
                )
        else:
            # Generate authorization URL
            logger.info("Generating Spotify authorization URL")
            auth_url = spotify_client.auth_manager.get_authorize_url()
            
            return func.HttpResponse(
                f"""
                <html>
                <body>
                    <h2>Spotify認証</h2>
                    <p>以下のリンクをクリックしてSpotifyにログインしてください：</p>
                    <a href="{auth_url}" target="_blank">Spotifyで認証</a>
                    <p>認証後、自動的にリダイレクトされます。</p>
                </body>
                </html>
                """,
                status_code=200,
                mimetype="text/html; charset=utf-8"
            )
    except Exception as e:
        logger.error(f"Unexpected error in spotify_auth: {str(e)}")
        return func.HttpResponse(
            "認証処理でエラーが発生しました。",
            status_code=500,
            mimetype="text/html; charset=utf-8"
        )


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_create_playlist",
    description="Create a new Spotify playlist",
    toolProperties=create_playlist_properties_json,
)
def spotify_create_playlist(context) -> str:
    """Handle creating a new Spotify playlist."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        
        logger.info(f"Creating playlist with arguments: {arguments}")
        playlist = spotify_client.create_playlist(
            name=arguments.get("name"),
            public=arguments.get("public", False),
            description=arguments.get("description", ""),
        )
        return json.dumps(playlist, indent=2)
        
    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"An error occurred with the Spotify Client: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "An internal server error occurred. Please try again later."


@app.route(route="spotify_auth", auth_level=func.AuthLevel.ANONYMOUS)
def spotify_auth(req: func.HttpRequest) -> func.HttpResponse:
    """Handle Spotify OAuth authentication flow."""
    try:
        # Check if this is a callback with authorization code
        code = req.params.get('code')
        error = req.params.get('error')
        
        if error:
            logger.error(f"OAuth error: {error}")
            return func.HttpResponse(
                f"認証エラー: {error}",
                status_code=400,
                mimetype="text/html; charset=utf-8"
            )
        
        if code:
            # Handle callback - exchange code for token
            try:
                logger.info("Handling OAuth callback with authorization code")
                token_info = spotify_client.auth_manager.get_access_token(code)
                
                # Store token in memory cache
                _access_token_cache['token'] = token_info
                logger.info("OAuth token successfully stored in memory cache")
                
                return func.HttpResponse(
                    """
                    <html>
                    <body>
                        <h2>Spotify認証完了！</h2>
                        <p>認証が正常に完了しました。このウィンドウを閉じてください。</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                    """,
                    status_code=200,
                    mimetype="text/html; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"Error exchanging authorization code: {str(e)}")
                return func.HttpResponse(
                    f"トークン交換エラー: {str(e)}",
                    status_code=400,
                    mimetype="text/html; charset=utf-8"
                )
        else:
            # Generate authorization URL
            logger.info("Generating Spotify authorization URL")
            auth_url = spotify_client.auth_manager.get_authorize_url()
            
            return func.HttpResponse(
                f"""
                <html>
                <body>
                    <h2>Spotify認証</h2>
                    <p>以下のリンクをクリックしてSpotifyにログインしてください：</p>
                    <a href="{auth_url}" target="_blank">Spotifyで認証</a>
                    <p>認証後、自動的にリダイレクトされます。</p>
                </body>
                </html>
                """,
                status_code=200,
                mimetype="text/html; charset=utf-8"
            )
    except Exception as e:
        logger.error(f"Unexpected error in spotify_auth: {str(e)}")
        return func.HttpResponse(
            "認証処理でエラーが発生しました。",
            status_code=500,
            mimetype="text/html; charset=utf-8"
        )


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_add_tracks_to_playlist",
    description="Add tracks to a specified playlist",
    toolProperties=add_tracks_to_playlist_properties_json,
)
def spotify_add_tracks_to_playlist(context) -> str:
    """Handle adding tracks to a playlist."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        
        logger.info(f"Adding tracks to playlist with arguments: {arguments}")
        playlist_id = arguments.get("playlist_id")
        track_ids = arguments.get("track_ids")
        position = arguments.get("position")
        result = spotify_client.add_tracks_to_playlist(playlist_id=playlist_id, track_ids=track_ids, position=position)
        return f"トラック追加完了！: {result}"
        
    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"An error occurred with the Spotify Client: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "An internal server error occurred. Please try again later."


@app.route(route="spotify_auth", auth_level=func.AuthLevel.ANONYMOUS)
def spotify_auth(req: func.HttpRequest) -> func.HttpResponse:
    """Handle Spotify OAuth authentication flow."""
    try:
        # Check if this is a callback with authorization code
        code = req.params.get('code')
        error = req.params.get('error')
        
        if error:
            logger.error(f"OAuth error: {error}")
            return func.HttpResponse(
                f"認証エラー: {error}",
                status_code=400,
                mimetype="text/html; charset=utf-8"
            )
        
        if code:
            # Handle callback - exchange code for token
            try:
                logger.info("Handling OAuth callback with authorization code")
                token_info = spotify_client.auth_manager.get_access_token(code)
                
                # Store token in memory cache
                _access_token_cache['token'] = token_info
                logger.info("OAuth token successfully stored in memory cache")
                
                return func.HttpResponse(
                    """
                    <html>
                    <body>
                        <h2>Spotify認証完了！</h2>
                        <p>認証が正常に完了しました。このウィンドウを閉じてください。</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                    """,
                    status_code=200,
                    mimetype="text/html; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"Error exchanging authorization code: {str(e)}")
                return func.HttpResponse(
                    f"トークン交換エラー: {str(e)}",
                    status_code=400,
                    mimetype="text/html; charset=utf-8"
                )
        else:
            # Generate authorization URL
            logger.info("Generating Spotify authorization URL")
            auth_url = spotify_client.auth_manager.get_authorize_url()
            
            return func.HttpResponse(
                f"""
                <html>
                <body>
                    <h2>Spotify認証</h2>
                    <p>以下のリンクをクリックしてSpotifyにログインしてください：</p>
                    <a href="{auth_url}" target="_blank">Spotifyで認証</a>
                    <p>認証後、自動的にリダイレクトされます。</p>
                </body>
                </html>
                """,
                status_code=200,
                mimetype="text/html; charset=utf-8"
            )
    except Exception as e:
        logger.error(f"Unexpected error in spotify_auth: {str(e)}")
        return func.HttpResponse(
            "認証処理でエラーが発生しました。",
            status_code=500,
            mimetype="text/html; charset=utf-8"
        )


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_add_track_to_liked_songs",
    description="Add a track to the user's Liked Songs (library)",
    toolProperties=add_track_to_liked_songs_properties_json,
)
def spotify_add_track_to_liked_songs(context) -> str:
    """Handle adding a track to liked songs."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        
        logger.info(f"Adding track to liked songs with arguments: {arguments}")
        track_id = arguments.get("track_id")
        result = spotify_client.add_track_to_liked_songs(track_id=track_id)
        return f"Added to liked songs! {result}"
        
    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"An error occurred with the Spotify Client: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "An internal server error occurred. Please try again later."


@app.route(route="spotify_auth", auth_level=func.AuthLevel.ANONYMOUS)
def spotify_auth(req: func.HttpRequest) -> func.HttpResponse:
    """Handle Spotify OAuth authentication flow."""
    try:
        # Check if this is a callback with authorization code
        code = req.params.get('code')
        error = req.params.get('error')
        
        if error:
            logger.error(f"OAuth error: {error}")
            return func.HttpResponse(
                f"認証エラー: {error}",
                status_code=400,
                mimetype="text/html; charset=utf-8"
            )
        
        if code:
            # Handle callback - exchange code for token
            try:
                logger.info("Handling OAuth callback with authorization code")
                token_info = spotify_client.auth_manager.get_access_token(code)
                
                # Store token in memory cache
                _access_token_cache['token'] = token_info
                logger.info("OAuth token successfully stored in memory cache")
                
                return func.HttpResponse(
                    """
                    <html>
                    <body>
                        <h2>Spotify認証完了！</h2>
                        <p>認証が正常に完了しました。このウィンドウを閉じてください。</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                    """,
                    status_code=200,
                    mimetype="text/html; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"Error exchanging authorization code: {str(e)}")
                return func.HttpResponse(
                    f"トークン交換エラー: {str(e)}",
                    status_code=400,
                    mimetype="text/html; charset=utf-8"
                )
        else:
            # Generate authorization URL
            logger.info("Generating Spotify authorization URL")
            auth_url = spotify_client.auth_manager.get_authorize_url()
            
            return func.HttpResponse(
                f"""
                <html>
                <body>
                    <h2>Spotify認証</h2>
                    <p>以下のリンクをクリックしてSpotifyにログインしてください：</p>
                    <a href="{auth_url}" target="_blank">Spotifyで認証</a>
                    <p>認証後、自動的にリダイレクトされます。</p>
                </body>
                </html>
                """,
                status_code=200,
                mimetype="text/html; charset=utf-8"
            )
    except Exception as e:
        logger.error(f"Unexpected error in spotify_auth: {str(e)}")
        return func.HttpResponse(
            "認証処理でエラーが発生しました。",
            status_code=500,
            mimetype="text/html; charset=utf-8"
        )