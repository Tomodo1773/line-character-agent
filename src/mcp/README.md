# MCP Azure Function

This Azure Function provides a sample implementation for Spotify integration using the Model Context Protocol (MCP).

## Features

- **Playlist Management**: Get user playlists and create new ones
- **Track Search**: Search for tracks by query
- **Daily Sync**: Timer-triggered function for daily Spotify data synchronization

## Endpoints

### GET /api/playlists
Returns a list of user playlists.

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": "37i9dQZF1DX0XUsuxWHRQd",
      "name": "RapCaviar",
      "description": "New music from hip-hop's finest",
      "external_urls": {
        "spotify": "https://open.spotify.com/playlist/37i9dQZF1DX0XUsuxWHRQd"
      },
      "tracks": {
        "total": 50
      }
    }
  ]
}
```

### GET /api/search?q={query}
Search for tracks by query parameter.

**Parameters:**
- `q` (required): Search query string

**Response:**
```json
{
  "status": "success",
  "query": "your search query",
  "data": [
    {
      "id": "4iV5W9uYEdYUVa79Axb7Rh",
      "name": "Sample Track for 'your search query'",
      "artists": [
        {
          "id": "1uNFoZAHBGtllmzznpCI3s",
          "name": "Sample Artist"
        }
      ],
      "album": {
        "id": "4aawyAB9vmqN3uQ7FjRGTy",
        "name": "Sample Album"
      },
      "duration_ms": 240000,
      "external_urls": {
        "spotify": "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"
      }
    }
  ]
}
```

### POST /api/playlists
Create a new playlist.

**Request Body:**
```json
{
  "name": "My New Playlist",
  "description": "Optional description"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Playlist 'My New Playlist' created successfully",
  "data": {
    "id": "37i9dQZF1DX0XUsuxWHRQd",
    "name": "My New Playlist",
    "description": "Optional description",
    "external_urls": {
      "spotify": "https://open.spotify.com/playlist/37i9dQZF1DX0XUsuxWHRQd"
    },
    "tracks": {
      "total": 0
    },
    "created": true
  }
}
```

## Timer Function

The `daily_spotify_sync` function runs daily at midnight (UTC) and can be used for:
- Synchronizing playlist data
- Analyzing music trends
- Updating recommendations
- Backing up user data

## Environment Variables

The following environment variables need to be configured:

- `SPOTIFY_CLIENT_ID`: Your Spotify app client ID
- `SPOTIFY_CLIENT_SECRET`: Your Spotify app client secret
- `SPOTIFY_REDIRECT_URI`: Your Spotify app redirect URI

## Development

This is sample code that provides the basic structure for a Spotify MCP integration. To implement real Spotify functionality, you would need to:

1. Register your application with Spotify Developer Dashboard
2. Implement OAuth2 authentication flow
3. Use the Spotify Web API to interact with real data
4. Add proper error handling and validation
5. Implement user session management

## Dependencies

- `azure-functions`: Azure Functions Python SDK
- `requests`: HTTP library for API calls
- `azure-identity`: Azure authentication
- `spotipy`: Spotify Web API Python library (for future implementation)