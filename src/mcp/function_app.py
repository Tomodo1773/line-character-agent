import json
import sys
from typing import Optional

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server  # , stdio_server
from pydantic import BaseModel, Field
from spotipy import SpotifyException

from spotify_mcp import spotify_api


def setup_logger():
    class Logger:
        def info(self, message):
            print(f"[INFO] {message}", file=sys.stderr)

        def error(self, message):
            print(f"[ERROR] {message}", file=sys.stderr)

    return Logger()


logger = setup_logger()
spotify_client = spotify_api.Client(logger)


server = Server("spotify-mcp")


# options =
class ToolModel(BaseModel):
    @classmethod
    def as_tool(cls):
        return types.Tool(name="Spotify" + cls.__name__, description=cls.__doc__, inputSchema=cls.model_json_schema())


class Playback(ToolModel):
    """Manages the current playback with the following actions:
    - get: Get information about user's current track.
    - start: Starts playing new item or resumes current playback if called with no uri.
    - pause: Pauses current playback.
    - skip: Skips current track.
    """

    action: str = Field(description="Action to perform: 'get', 'start', 'pause' or 'skip'.")
    spotify_uri: Optional[str] = Field(
        default=None, description="Spotify uri of item to play for 'start' action. " + "If omitted, resumes current playback."
    )
    num_skips: Optional[int] = Field(default=1, description="Number of tracks to skip for `skip` action.")


class Queue(ToolModel):
    """Manage the playback queue - get the queue or add tracks."""

    action: str = Field(description="Action to perform: 'add' or 'get'.")
    track_id: Optional[str] = Field(default=None, description="Track ID to add to queue (required for add action)")


class GetInfo(ToolModel):
    """Get detailed information about a Spotify item (track, album, artist, or playlist)."""

    item_uri: str = Field(
        description="URI of the item to get information about. "
        + "If 'playlist' or 'album', returns its tracks. "
        + "If 'artist', returns albums and top tracks."
    )
    # qtype: str = Field(default="track", description="Type of item: 'track', 'album', 'artist', or 'playlist'. "
    #                                                 )


class Search(ToolModel):
    """Search for tracks, albums, artists, or playlists on Spotify."""

    query: str = Field(description="query term")
    qtype: Optional[str] = Field(
        default="track",
        description="Type of items to search for (track, album, artist, playlist, " + "or comma-separated combination)",
    )
    limit: Optional[int] = Field(default=10, description="Maximum number of items to return")


class CreatePlaylist(ToolModel):
    """Create a new Spotify playlist."""

    name: str = Field(description="Name of the playlist to create")
    public: Optional[bool] = Field(default=False, description="Whether the playlist should be public (default is private)")
    description: Optional[str] = Field(default="", description="Description for the playlist")


class AddTracksToPlaylist(ToolModel):
    """Tool for adding tracks to a specified playlist"""

    playlist_id: str = Field(description="ID of the playlist to add tracks to")
    track_ids: list[str] = Field(description="List of track IDs to add (up to 100)")
    position: Optional[int] = Field(default=None, description="Position to insert tracks (optional, default is end)")


class AddTrackToLikedSongs(ToolModel):
    """Add a track to the user's Liked Songs (library)."""

    track_id: str = Field(description="ID of the track to add to liked songs")


@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    return []


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    return []


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    logger.info("Listing available tools")
    # await server.request_context.session.send_notification("are you recieving this notification?")
    tools = [
        Playback.as_tool(),
        Search.as_tool(),
        Queue.as_tool(),
        GetInfo.as_tool(),
        CreatePlaylist.as_tool(),
        AddTracksToPlaylist.as_tool(),
        AddTrackToLikedSongs.as_tool(),
    ]
    logger.info(f"Available tools: {[tool.name for tool in tools]}")
    return tools


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    assert name[:7] == "Spotify", f"Unknown tool: {name}"
    try:
        match name[7:]:
            case "Playback":
                action = arguments.get("action")
                match action:
                    case "get":
                        logger.info("Attempting to get current track")
                        curr_track = spotify_client.get_current_track()
                        if curr_track:
                            logger.info(f"Current track retrieved: {curr_track.get('name', 'Unknown')}")
                            return [types.TextContent(type="text", text=json.dumps(curr_track, indent=2))]
                        logger.info("No track currently playing")
                        return [types.TextContent(type="text", text="No track playing.")]
                    case "start":
                        logger.info(f"Starting playback with arguments: {arguments}")
                        spotify_client.start_playback(spotify_uri=arguments.get("spotify_uri"))
                        logger.info("Playback started successfully")
                        return [types.TextContent(type="text", text="Playback starting.")]
                    case "pause":
                        logger.info("Attempting to pause playback")
                        spotify_client.pause_playback()
                        logger.info("Playback paused successfully")
                        return [types.TextContent(type="text", text="Playback paused.")]
                    case "skip":
                        num_skips = int(arguments.get("num_skips", 1))
                        logger.info(f"Skipping {num_skips} tracks.")
                        spotify_client.skip_track(n=num_skips)
                        return [types.TextContent(type="text", text="Skipped to next track.")]

            case "Search":
                logger.info(f"Performing search with arguments: {arguments}")
                search_results = spotify_client.search(
                    query=arguments.get("query", ""), qtype=arguments.get("qtype", "track"), limit=arguments.get("limit", 10)
                )
                logger.info("Search completed successfully.")
                return [types.TextContent(type="text", text=json.dumps(search_results, indent=2))]

            case "Queue":
                logger.info(f"Queue operation with arguments: {arguments}")
                action = arguments.get("action")

                match action:
                    case "add":
                        track_id = arguments.get("track_id")
                        if not track_id:
                            logger.error("track_id is required for add to queue.")
                            return [types.TextContent(type="text", text="track_id is required for add action")]
                        spotify_client.add_to_queue(track_id)
                        return [types.TextContent(type="text", text="Track added to queue.")]

                    case "get":
                        queue = spotify_client.get_queue()
                        return [types.TextContent(type="text", text=json.dumps(queue, indent=2))]

                    case _:
                        return [
                            types.TextContent(
                                type="text",
                                text=f"Unknown queue action: {action}. Supported actions are: add, remove, and get.",
                            )
                        ]

            case "GetInfo":
                logger.info(f"Getting item info with arguments: {arguments}")
                item_info = spotify_client.get_info(item_uri=arguments.get("item_uri"))
                return [types.TextContent(type="text", text=json.dumps(item_info, indent=2))]

            case "CreatePlaylist":
                logger.info(f"Creating playlist with arguments: {arguments}")
                playlist = spotify_client.create_playlist(
                    name=arguments.get("name"),
                    public=arguments.get("public", False),
                    description=arguments.get("description", ""),
                )
                return [types.TextContent(type="text", text=json.dumps(playlist, indent=2))]

            case "AddTracksToPlaylist":
                logger.info(f"Adding tracks to playlist with arguments: {arguments}")
                playlist_id = arguments.get("playlist_id")
                track_ids = arguments.get("track_ids")
                position = arguments.get("position")
                result = spotify_client.add_tracks_to_playlist(playlist_id=playlist_id, track_ids=track_ids, position=position)
                return [types.TextContent(type="text", text=f"トラック追加完了！: {result}")]

            case "AddTrackToLikedSongs":
                logger.info(f"Adding track to liked songs with arguments: {arguments}")
                track_id = arguments.get("track_id")
                result = spotify_client.add_track_to_liked_songs(track_id=track_id)
                return [types.TextContent(type="text", text=f"Added to liked songs! {result}")]

            case _:
                error_msg = f"Unknown tool: {name}"
                logger.error(error_msg)
                return [types.TextContent(type="text", text=error_msg)]
    except SpotifyException as se:
        error_msg = f"Spotify Client error occurred: {str(se)}"
        logger.error(error_msg)
        return [types.TextContent(type="text", text=f"An error occurred with the Spotify Client: {str(se)}")]
    except Exception as e:
        error_msg = f"Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return [types.TextContent(type="text", text=error_msg)]


async def main():
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    except Exception as e:
        logger.error(f"Server error occurred: {str(e)}")
        raise
