import json
import logging
import os

import azure.functions as func
from openai import OpenAI
from spotify_api import Client
from spotipy import SpotifyException

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
    ToolProperty(
        "qtype",
        "string",
        "Type of items to search for (track, album, artist, or comma-separated combination) (default: track). Use spotify_search_my_playlists for playlist searches instead",
    ),
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
    ToolProperty("track_id", "string", "ID of the track to add to the playlist"),
    ToolProperty("position", "number", "Position to insert tracks (optional, default is end)"),
]

add_track_to_liked_songs_properties = [
    ToolProperty("track_id", "string", "ID of the track to add to liked songs"),
]

search_my_playlists_properties = [
    ToolProperty("query", "string", "Search query to match against playlist names"),
    ToolProperty("limit", "number", "Maximum number of results to return (default: 50)"),
]


# Convert tool properties to JSON
playback_properties_json = json.dumps([prop.to_dict() for prop in playback_properties])
search_properties_json = json.dumps([prop.to_dict() for prop in search_properties])
queue_properties_json = json.dumps([prop.to_dict() for prop in queue_properties])
get_info_properties_json = json.dumps([prop.to_dict() for prop in get_info_properties])
create_playlist_properties_json = json.dumps([prop.to_dict() for prop in create_playlist_properties])
add_tracks_to_playlist_properties_json = json.dumps([prop.to_dict() for prop in add_tracks_to_playlist_properties])
add_track_to_liked_songs_properties_json = json.dumps([prop.to_dict() for prop in add_track_to_liked_songs_properties])
search_my_playlists_properties_json = json.dumps([prop.to_dict() for prop in search_my_playlists_properties])


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


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_search",
    description="Search for tracks, albums, or artists on Spotify (use spotify_search_my_playlists for playlist searches)",
    toolProperties=search_properties_json,
)
def spotify_search(context) -> str:
    """Handle Spotify search."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})

        logger.info(f"Performing search with arguments: {arguments}")
        search_results = spotify_client.search(
            query=arguments.get("query", ""), qtype=arguments.get("qtype", "track"), limit=arguments.get("limit", 10)
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
        name = arguments.get("name", "")

        logger.info(f"Creating playlist with arguments: {arguments}")

        if not name:
            logger.error("Playlist name is required")
            return "Playlist name is required."

        # Check if playlist with same name already exists
        logger.info(f"Checking for existing playlists with name: {name}")
        search_results = spotify_client.search_my_playlists(query=name, limit=50)
        existing_playlists = search_results.get("playlists", [])

        # Check for exact match
        exact_match = next((p for p in existing_playlists if p.get("name", "").lower() == name.lower()), None)

        if exact_match:
            logger.info(f"Found existing playlist with same name: {name}")
            return f"A playlist with the name '{name}' already exists. Playlist ID: {exact_match.get('id')}"

        # Create playlist if no duplicate found
        logger.info(f"No duplicate found, creating new playlist: {name}")
        playlist = spotify_client.create_playlist(
            name=name,
            public=arguments.get("public", False),
            description=arguments.get("description", ""),
        )
        logger.info(f"Successfully created playlist: {name}")
        return json.dumps(playlist, indent=2)

    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"An error occurred with the Spotify Client: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "An internal server error occurred. Please try again later."


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

        logger.info(f"Adding track to playlist with arguments: {arguments}")
        playlist_id = arguments.get("playlist_id")
        track_id = arguments.get("track_id")
        position = arguments.get("position")

        # track_idをリストにして渡す（API互換のため）
        try:
            playlist_result = spotify_client.add_tracks_to_playlist(
                playlist_id=playlist_id, track_ids=[track_id], position=position
            )
            logger.info("Successfully added track to playlist")
        except SpotifyException as se:
            error_msg = f"Failed to add track to playlist: {str(se)}"
            logger.error(error_msg)
            return "プレイリストへのトラック追加に失敗しました。"

        # プレイリスト追加後、お気に入りにも追加
        try:
            liked_result = spotify_client.add_track_to_liked_songs(track_id=track_id)
            logger.info("Successfully added track to liked songs")
            return f"トラック追加完了！{playlist_result} {liked_result}"
        except SpotifyException as se:
            logger.error(f"Failed to add track to liked songs: {str(se)}")
            return f"トラックはプレイリストに追加されましたが、お気に入りへの追加に失敗しました。Playlist: {playlist_result}"
        except Exception as e:
            logger.error(f"Unexpected error while adding track to liked songs: {str(e)}")
            return f"トラックはプレイリストに追加されましたが、お気に入りへの追加中に予期しないエラーが発生しました。Playlist: {playlist_result}"

    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "予期しないエラーが発生しました。もう一度お試しください。"


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


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="spotify_search_my_playlists",
    description="Search for playlists owned by the current user",
    toolProperties=search_my_playlists_properties_json,
)
def spotify_search_my_playlists(context) -> str:
    """Handle searching user's own playlists."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        query = arguments.get("query", "")
        limit = int(arguments.get("limit", 50))

        logger.info(f"Searching user's playlists with query: '{query}', limit: {limit}")

        if not query:
            logger.error("Search query is required")
            return "検索クエリが必要です。検索クエリを入力してください。"

        search_results = spotify_client.search_my_playlists(query=query, limit=limit)

        if not search_results.get("playlists") or len(search_results["playlists"]) == 0:
            logger.info("No playlists found for the search query")
            return f"検索クエリ '{query}' に一致するプレイリストが見つかりませんでした。"

        num_found = len(search_results["playlists"])
        logger.info(f"Found {num_found} playlists matching the search query")

        return json.dumps(search_results, indent=2)

    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return f"Spotify クライアントでエラーが発生しました: {str(se)}"
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return "内部サーバーエラーが発生しました。再度お試しください。"


# OpenAI Web Search Tool
openai_search_properties = [
    ToolProperty(
        "query", "string", "A search request in sentence form (make it as specific as possible and include context)."
    ),
]
openai_search_properties_json = json.dumps([prop.to_dict() for prop in openai_search_properties])


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="openai_web_search",
    description="MCP tool that uses OpenAI Responses API with gpt-5.1 to retrieve the latest information from the web. Submit a query to search the web and get up-to-date information.",
    toolProperties=openai_search_properties_json,
)
def openai_web_search(context) -> str:
    """MCP tool for web search using OpenAI Responses API with gpt-5.1."""
    try:
        content = json.loads(context)
        arguments = content.get("arguments", {})
        query = arguments.get("query", "")

        if not query:
            return "検索クエリが必要です。クエリを入力してください。"

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "OPENAI_API_KEYが環境変数にセットされていません。APIキーをセットしてから利用してください。"

        client = OpenAI(api_key=api_key)

        instructions = """
You are a helpful AI assistant with access to web search.

Rules:
1. Provide only the final answer. It is important that you do not include any explanation on the steps below.
2. Do not show the intermediate steps information.

Steps:
1. Decide if the answer should be a brief sentence or a list of suggestions.
2. If it is a list of suggestions, first, write a brief and natural introduction based on the original query.
3. Followed by a list of suggestions, each suggestion should be split by two newlines.
"""

        response = client.responses.create(
            model="gpt-5.1",
            input=query,
            instructions=instructions,
        )

        return response.output_text
    except Exception as e:
        logger.error(f"OpenAI Web検索でエラー: {str(e)}")
        return f"OpenAI Web検索でエラーが発生しました: {str(e)}"
