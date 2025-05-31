# MCP Spotify Azure Function

This Azure Function provides Spotify integration using the Model Context Protocol (MCP) with OAuth authentication support.

## Features

- **OAuth Authentication**: Complete Spotify OAuth flow for remote environments
- **Playback Control**: Get current track, start/pause/skip playback
- **Search**: Search for tracks, albums, artists, and playlists
- **Queue Management**: Add tracks to queue and view current queue
- **Playlist Management**: Create playlists and add tracks
- **Library Management**: Add tracks to liked songs
- **Track Information**: Get detailed track/album/artist/playlist information

## Authentication

### OAuth Authentication Endpoints

#### GET /api/spotify_auth
Initiates or handles the Spotify OAuth authentication flow.

**初回アクセス (Initial Access):**
- Returns HTML page with Spotify login link
- User clicks link to authenticate with Spotify
- After authentication, user is redirected back to this endpoint

**コールバック (Callback):**
- Receives authorization code from Spotify
- Exchanges code for access token
- Stores token in memory for MCP tools to use
- Returns success page

#### GET /api/spotify_auth_status
Check current authentication status.

**Response:**
```json
{
  "authenticated": true,
  "auth_url": null
}
```

or

```json
{
  "authenticated": false,
  "auth_url": "https://your-function.azurewebsites.net/api/spotify_auth"
}
```

### Setup Instructions

1. **Spotify Developer Console Settings:**
   - Redirect URI: `https://your-function.azurewebsites.net/api/spotify_auth`
   
2. **Environment Variables:**
   - `SPOTIFY_CLIENT_ID`: Your Spotify app client ID
   - `SPOTIFY_CLIENT_SECRET`: Your Spotify app client secret  
   - `SPOTIFY_REDIRECT_URI`: `https://your-function.azurewebsites.net/api/spotify_auth`

3. **Authentication Flow:**
   - Navigate to `/api/spotify_auth` in browser
   - Click the Spotify authentication link
   - Complete Spotify login
   - Token will be stored for MCP tools

## MCP Tools

The following MCP tools are available via the `mcpToolTrigger` system:

### spotify_playback
Manages the current playback with actions: get, start, pause, skip

**Parameters:**
- `action` (string): Action to perform: 'get', 'start', 'pause' or 'skip'
- `spotify_uri` (string, optional): Spotify URI for 'start' action
- `num_skips` (number, optional): Number of tracks to skip for 'skip' action (default: 1)

### spotify_search
Search for tracks, albums, artists, or playlists on Spotify

**Parameters:**
- `query` (string): Search query term
- `qtype` (string, optional): Type to search for - track, album, artist, playlist (default: track)
- `limit` (number, optional): Maximum number of items to return (default: 10)

### spotify_queue
Manage the playback queue - get the queue or add tracks

**Parameters:**
- `action` (string): Action to perform: 'add' or 'get'
- `track_id` (string): Track ID to add to queue (required for add action)

### spotify_get_info
Get detailed information about a Spotify item (track, album, artist, or playlist)

**Parameters:**
- `item_uri` (string): URI of the item to get information about

### spotify_create_playlist
Create a new Spotify playlist

**Parameters:**
- `name` (string): Name of the playlist to create
- `public` (boolean, optional): Whether the playlist should be public (default: false)
- `description` (string, optional): Description for the playlist

### spotify_add_tracks_to_playlist
Add tracks to a specified playlist

**Parameters:**
- `playlist_id` (string): ID of the playlist to add tracks to
- `track_ids` (array): List of track IDs to add (up to 100)
- `position` (number, optional): Position to insert tracks (default: end)

### spotify_add_track_to_liked_songs
Add a track to the user's Liked Songs (library)

**Parameters:**
- `track_id` (string): ID of the track to add to liked songs

## Token Management

- **Memory Storage**: Tokens are stored in memory for simplicity
- **Auto Re-authentication**: Functions restart will require re-authentication
- **Security**: Tokens are not persisted to disk or database

## Dependencies

- `azure-functions`: Azure Functions Python SDK
- `spotipy`: Spotify Web API Python library
- `python-dotenv`: Environment variable management