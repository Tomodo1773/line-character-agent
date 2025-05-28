import json
import logging
import os
from typing import Dict, List, Any

import azure.functions as func

app = func.FunctionApp()

@app.function_name(name="SpotifyPlaylistGet")
@app.route(route="playlists", auth_level=func.AuthLevel.FUNCTION)
def get_playlists(req: func.HttpRequest) -> func.HttpResponse:
    """
    Sample MCP Spotify function to get user playlists
    """
    logging.info('Python HTTP trigger function processed a request for playlists.')
    
    try:
        # Sample response for MCP Spotify playlists
        sample_playlists = [
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
            },
            {
                "id": "37i9dQZF1DXcBWIGoYBM5M",
                "name": "Today's Top Hits",
                "description": "The most played songs right now",
                "external_urls": {
                    "spotify": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
                },
                "tracks": {
                    "total": 50
                }
            }
        ]
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "data": sample_playlists
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error processing playlists request: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": f"Internal server error: {str(e)}"
            }),
            status_code=500,
            mimetype="application/json"
        )

@app.function_name(name="SpotifyTrackSearch")
@app.route(route="search", auth_level=func.AuthLevel.FUNCTION)
def search_tracks(req: func.HttpRequest) -> func.HttpResponse:
    """
    Sample MCP Spotify function to search for tracks
    """
    logging.info('Python HTTP trigger function processed a search request.')
    
    try:
        # Get query parameter
        query = req.params.get('q')
        if not query:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "Missing query parameter 'q'"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Sample search results
        sample_tracks = [
            {
                "id": "4iV5W9uYEdYUVa79Axb7Rh",
                "name": f"Sample Track for '{query}'",
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
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "query": query,
                "data": sample_tracks
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error processing search request: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": f"Internal server error: {str(e)}"
            }),
            status_code=500,
            mimetype="application/json"
        )

@app.function_name(name="SpotifyPlaylistCreate")
@app.route(route="playlists", auth_level=func.AuthLevel.FUNCTION, methods=["POST"])
def create_playlist(req: func.HttpRequest) -> func.HttpResponse:
    """
    Sample MCP Spotify function to create a playlist
    """
    logging.info('Python HTTP trigger function processed a create playlist request.')
    
    try:
        # Parse request body
        req_body = req.get_json()
        if not req_body:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "Missing request body"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        playlist_name = req_body.get('name')
        description = req_body.get('description', '')
        
        if not playlist_name:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "Missing 'name' field in request body"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Sample playlist creation response
        new_playlist = {
            "id": "37i9dQZF1DX0XUsuxWHRQd",
            "name": playlist_name,
            "description": description,
            "external_urls": {
                "spotify": "https://open.spotify.com/playlist/37i9dQZF1DX0XUsuxWHRQd"
            },
            "tracks": {
                "total": 0
            },
            "created": True
        }
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": f"Playlist '{playlist_name}' created successfully",
                "data": new_playlist
            }),
            status_code=201,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error processing create playlist request: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": f"Internal server error: {str(e)}"
            }),
            status_code=500,
            mimetype="application/json"
        )

@app.timer_trigger(schedule="0 0 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False) 
def daily_spotify_sync(myTimer: func.TimerRequest) -> None:
    """
    Sample timer function for daily Spotify data synchronization
    """
    logging.info('Daily Spotify sync timer function started.')
    
    try:
        # Sample daily sync logic
        sync_stats = {
            "playlists_processed": 5,
            "tracks_analyzed": 250,
            "recommendations_updated": 10
        }
        
        logging.info(f"Daily sync completed: {sync_stats}")
        
    except Exception as e:
        logging.error(f"Error during daily sync: {str(e)}")

if __name__ == "__main__":
    # For local testing
    print("MCP Spotify Function App - Sample Code")