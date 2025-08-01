import logging
import os
from typing import Dict, List, Optional

import spotipy
import utils
from dotenv import load_dotenv
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")


class MemoryCacheHandler(CacheHandler):
    """
    In-memory cache handler for Azure Functions environment.
    Stores tokens in memory instead of files.
    """

    def __init__(self, token_cache):
        self.token_cache = token_cache

    def get_cached_token(self):
        """Get token from memory cache."""
        return self.token_cache.get("token")

    def save_token_to_cache(self, token_info):
        """Save token to memory cache."""
        self.token_cache["token"] = token_info


print(f"CLIENT_ID: {CLIENT_ID}")
SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
    "user-read-currently-playing",  # spotify connect
    "app-remote-control",
    "streaming",  # playback
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
    # playlists
    "user-read-playback-position",
    "user-top-read",
    "user-read-recently-played",  # listening history
    "user-library-modify",
    "user-library-read",  # library
]


class Client:
    def __init__(self, logger: logging.Logger, token_cache=None):
        """Initialize Spotify client with necessary permissions"""
        self.logger = logger
        self.token_cache = token_cache or {}

        # Required scopes for playlist creation, playback control, and library modification
        scope = ",".join(SCOPES)

        # Use memory cache handler for Azure Functions
        cache_handler = MemoryCacheHandler(self.token_cache)
        self.cache_handler = cache_handler
        self.auth_manager = SpotifyOAuth(
            scope=scope,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri="http://localhost:8080/callback",  # ダミー値（リフレッシュトークン使用時は不要）
            cache_handler=cache_handler,
        )
        # --- ここからリフレッシュトークン対応 ---
        if REFRESH_TOKEN:
            # すでにリフレッシュトークンがある場合は、アクセストークンを取得してキャッシュ
            token_info = self.auth_manager.refresh_access_token(REFRESH_TOKEN)
            self.cache_handler.save_token_to_cache(token_info)
        self.sp = spotipy.Spotify(auth_manager=self.auth_manager)

        self.username = None

    @utils.auth_required
    def set_username(self):
        self.username = self.sp.current_user()["display_name"]

    @utils.auth_required
    def search(self, query: str, qtype: str = "track", limit=10):
        """
        Searches based of query term.
        - query: query term
        - qtype: the types of items to return. One or more of 'artist', 'album',  'track', 'playlist'.
                 If multiple types are desired, pass in a comma separated string; e.g. 'track,album'
        - limit: max # items to return
        """
        if self.username is None:
            self.set_username()
        results = self.sp.search(q=query, limit=limit, type=qtype)
        if not results:
            raise ValueError("No search results found.")
        return utils.parse_search_results(results, qtype, self.username)

    def recommendations(self, artists: Optional[List] = None, tracks: Optional[List] = None, limit=20):
        # doesnt work
        recs = self.sp.recommendations(seed_artists=artists, seed_tracks=tracks, limit=limit)
        return recs

    def get_info(self, item_uri: str) -> dict:
        """
        Returns more info about item.
        - item_uri: uri. Looks like 'spotify:track:xxxxxx', 'spotify:album:xxxxxx', etc.
        """
        _, qtype, item_id = item_uri.split(":")
        match qtype:
            case "track":
                return utils.parse_track(self.sp.track(item_id), detailed=True)
            case "album":
                album_info = utils.parse_album(self.sp.album(item_id), detailed=True)
                return album_info
            case "artist":
                artist_info = utils.parse_artist(self.sp.artist(item_id), detailed=True)
                albums = self.sp.artist_albums(item_id)
                top_tracks = self.sp.artist_top_tracks(item_id)["tracks"]
                albums_and_tracks = {"albums": albums, "tracks": {"items": top_tracks}}
                parsed_info = utils.parse_search_results(albums_and_tracks, qtype="album,track")
                artist_info["top_tracks"] = parsed_info["tracks"]
                artist_info["albums"] = parsed_info["albums"]

                return artist_info
            case "playlist":
                if self.username is None:
                    self.set_username()
                playlist = self.sp.playlist(item_id)
                self.logger.info(f"playlist info is {playlist}")
                playlist_info = utils.parse_playlist(playlist, self.username, detailed=True)

                return playlist_info

        raise ValueError(f"Unknown qtype {qtype}")

    def get_current_track(self) -> Optional[Dict]:
        """Get information about the currently playing track"""
        try:
            # current_playback vs current_user_playing_track?
            current = self.sp.current_user_playing_track()
            if not current:
                self.logger.info("No playback session found")
                return None
            if current.get("currently_playing_type") != "track":
                self.logger.info("Current playback is not a track")
                return None

            track_info = utils.parse_track(current["item"])
            if "is_playing" in current:
                track_info["is_playing"] = current["is_playing"]

            self.logger.info(f"Current track: {track_info.get('name', 'Unknown')} by {track_info.get('artist', 'Unknown')}")
            return track_info
        except Exception:
            self.logger.error("Error getting current track info.")
            raise

    @utils.device_required
    def start_playback(self, spotify_uri=None, device=None):
        """
        Starts spotify playback of uri. If spotify_uri is omitted, resumes current playback.
        - spotify_uri: ID of resource to play, or None. Typically looks like 'spotify:track:xxxxxx' or 'spotify:album:xxxxxx'.
        """
        try:
            self.logger.info(f"Starting playback for spotify_uri: {spotify_uri} on {device}")
            if not spotify_uri:
                if self.is_track_playing():
                    self.logger.info("No track_id provided and playback already active.")
                    return
                if not self.get_current_track():
                    raise ValueError("No track_id provided and no current playback to resume.")

            if spotify_uri is not None:
                if spotify_uri.startswith("spotify:track:"):
                    uris = [spotify_uri]
                    context_uri = None
                else:
                    uris = None
                    context_uri = spotify_uri
            else:
                uris = None
                context_uri = None

            device_id = device.get("id") if device else None

            self.logger.info(f"Starting playback of on {device}: context_uri={context_uri}, uris={uris}")
            result = self.sp.start_playback(uris=uris, context_uri=context_uri, device_id=device_id)
            self.logger.info(f"Playback result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error starting playback: {str(e)}.")
            raise

    @utils.device_required
    def pause_playback(self, device=None):
        """Pauses playback."""
        playback = self.sp.current_playback()
        if playback and playback.get("is_playing"):
            self.sp.pause_playback(device.get("id") if device else None)

    @utils.device_required
    def add_to_queue(self, track_id: str, device=None):
        """
        Adds track to queue.
        - track_id: ID of track to play.
        """
        self.sp.add_to_queue(track_id, device.get("id") if device else None)

    @utils.device_required
    def get_queue(self, device=None):
        """Returns the current queue of tracks."""
        queue_info = self.sp.queue()
        queue_info["currently_playing"] = self.get_current_track()

        queue_info["queue"] = [utils.parse_track(track) for track in queue_info.pop("queue")]

        return queue_info

    def get_liked_songs(self):
        # todo
        results = self.sp.current_user_saved_tracks()
        for idx, item in enumerate(results["items"]):
            track = item["track"]
            print(idx, track["artists"][0]["name"], " – ", track["name"])

    @utils.auth_required
    def add_track_to_liked_songs(self, track_id: str):
        """
        Add a track to the user's Liked Songs (library).
        - track_id: The ID of the track to add.
        """
        self.logger.info(f"Adding track {track_id} to liked songs.")
        result = self.sp.current_user_saved_tracks_add(tracks=[track_id])
        self.logger.info("Add to liked songs result")
        return result

    def is_track_playing(self) -> bool:
        """Returns if a track is actively playing."""
        curr_track = self.get_current_track()
        if not curr_track:
            return False
        if curr_track.get("is_playing"):
            return True
        return False

    def get_devices(self) -> dict:
        return self.sp.devices()["devices"]

    def is_active_device(self):
        return any([device.get("is_active") for device in self.get_devices()])

    def _get_candidate_device(self):
        devices = self.get_devices()
        if not devices:
            raise ConnectionError("No active device. Is Spotify open?")
        for device in devices:
            if device.get("is_active"):
                return device
        self.logger.info(f"No active device, assigning {devices[0]['name']}.")
        return devices[0]

    def auth_ok(self) -> bool:
        try:
            token = self.cache_handler.get_cached_token()
            if token is None:
                self.logger.info("Auth check result: no token exists")
                return False

            is_expired = self.auth_manager.is_token_expired(token)
            self.logger.info(f"Auth check result: {'valid' if not is_expired else 'expired'}")
            return not is_expired  # Return True if token is NOT expired
        except Exception as e:
            self.logger.error(f"Error checking auth status: {str(e)}")
            return False  # Return False on error rather than raising

    def auth_refresh(self):
        self.auth_manager.validate_token(self.cache_handler.get_cached_token())

    def skip_track(self, n=1):
        # todo: Better error handling
        for _ in range(n):
            self.sp.next_track()

    def previous_track(self):
        self.sp.previous_track()

    def seek_to_position(self, position_ms):
        self.sp.seek_track(position_ms=position_ms)

    def set_volume(self, volume_percent):
        self.sp.volume(volume_percent)

    @utils.auth_required
    def create_playlist(self, name: str, public: bool = False, description: str = ""):
        """
        Create a new Spotify playlist.
        - name: Playlist name
        - public: Whether the playlist is public (default: False)
        - description: Playlist description
        """
        if self.username is None:
            self.set_username()
        user_id = self.sp.current_user()["id"]
        playlist = self.sp.user_playlist_create(user=user_id, name=name, public=public, description=description)
        self.logger.info(f"Created playlist: {playlist}")
        return playlist

    @utils.auth_required
    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str], position: int = None):
        """
        Add tracks to a specified playlist.
        - playlist_id: The ID of the playlist
        - track_ids: List of track IDs to add (up to 100)
        - position: Position to insert the tracks (optional, default is end)
        """
        self.logger.info(f"Adding tracks {track_ids} to playlist {playlist_id} at position {position}")
        result = self.sp.user_playlist_add_tracks(
            user=self.sp.current_user()["id"], playlist_id=playlist_id, tracks=track_ids, position=position
        )
        self.logger.info(f"Add tracks result: {result}")
        return result

    @utils.auth_required
    def search_my_playlists(self, query: str, limit: int = 50):
        """
        Search for playlists owned by the current user.
        - query: Search query to match against playlist names
        - limit: Maximum number of results to return
        """
        if self.username is None:
            self.set_username()

        me_id = self.sp.current_user()["id"]
        search_query = query.casefold().strip()
        matching_playlists = []

        # Get user's playlists with pagination
        offset = 0
        page_limit = min(limit, 50)  # Spotify API limit is 50

        while len(matching_playlists) < limit:
            page = self.sp.current_user_playlists(limit=page_limit, offset=offset)

            for playlist in page["items"]:
                if len(matching_playlists) >= limit:
                    break

                # Check if playlist is owned by user and matches search query
                if playlist["owner"]["id"] == me_id and search_query in playlist["name"].casefold().strip():
                    matching_playlists.append(playlist)

            # Check if we've reached the end of results
            if not page.get("next"):
                break

            offset += page_limit
        self.logger.info(f"Found {len(matching_playlists)} matching playlists for query '{query}'")

        # Parse results using existing utility function
        parsed_results = {
            "playlists": {
                "href": f"search?q={query.replace(' ', '%20')}&type=playlist&limit={limit}",
                "items": matching_playlists,  # 生のプレイリストデータをそのまま渡す
                "limit": limit,
                "next": None,
                "offset": 0,
                "previous": None,
                "total": len(matching_playlists),
            }
        }

        return utils.parse_search_results(parsed_results, "playlist", self.username)

    @utils.auth_required
    def has_duplicate_playlist(self, name: str):
        """
        Check if a playlist with the given name already exists in user's playlists.
        Returns tuple of (has_duplicate: bool, playlist_id: str or None)
        - name: Playlist name to check for duplicates
        """
        if self.username is None:
            self.set_username()

        me_id = self.sp.current_user()["id"]
        target = name.casefold().strip()
        limit, offset = 50, 0

        while True:
            page = self.sp.current_user_playlists(limit=limit, offset=offset)
            for playlist in page["items"]:
                if playlist["owner"]["id"] == me_id and playlist["name"].casefold().strip() == target:
                    self.logger.info(f"Found duplicate playlist: {playlist['name']} (ID: {playlist['id']})")
                    return True, playlist["id"]

            if not page.get("next"):
                break
            offset += limit

        self.logger.info(f"No duplicate playlist found for name: {name}")
        return False, None
