import re
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from cachetools import TTLCache
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from youtubesearchpython import VideosSearch
import config
import asyncio
from BrandrdXMusic.utils.logger import LOGGER

class SpotifyAPI:
    def __init__(self):
        self.regex = r"^(https:\/\/open.spotify\.com\/)(.*)$"
        self.client_id = config.SPOTIFY_CLIENT_ID
        self.client_secret = config.SPOTIFY_CLIENT_SECRET
        
        # Initialize caches with optimized settings
        self.track_cache = TTLCache(maxsize=1000, ttl=1800)  # 30 minutes cache
        self.playlist_cache = TTLCache(maxsize=200, ttl=3600)  # 1 hour cache
        
        # Rate limiting variables
        self.last_request_time = 0
        self.request_delay = 0.5  # 500ms between requests
        
        # Initialize Spotify client with better configuration
        if self.client_id and self.client_secret:
            auth_manager = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            self.spotify = spotipy.Spotify(
                auth_manager=auth_manager,
                retries=5,
                status_forcelist=[429, 500, 502, 503, 504],
                backoff_factor=0.5
            )
        else:
            LOGGER.warning("Spotify credentials not configured!")
            self.spotify = None

    async def _rate_limit(self):
        """Enforce rate limiting between requests"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.request_delay:
            await asyncio.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    async def valid(self, link: str):
        """Check if link is a valid Spotify URL"""
        return bool(re.match(self.regex, link))

    async def track(self, link: str):
        """Get track details from Spotify"""
        if not self.spotify:
            raise Exception("Spotify client not initialized")
            
        cache_key = f"track_{link}"
        if cache_key in self.track_cache:
            return self.track_cache[cache_key]

        await self._rate_limit()
        
        try:
            track = self.spotify.track(link)
            if not track:
                raise Exception("Track not found")
                
            # Build search query
            artists = ", ".join(
                artist["name"] 
                for artist in track["artists"] 
                if artist["name"] != "Various Artists"
            )
            search_query = f"{track['name']} {artists}"
            
            # Search YouTube
            results = VideosSearch(search_query, limit=1)
            video = (await results.next())["result"][0]
            
            track_details = {
                "title": video["title"],
                "link": video["link"],
                "vidid": video["id"],
                "duration_min": video["duration"],
                "thumb": video["thumbnails"][0]["url"].split("?")[0],
                "spotify": {
                    "name": track["name"],
                    "artists": [a["name"] for a in track["artists"]],
                    "album": track["album"]["name"],
                    "url": track["external_urls"]["spotify"]
                }
            }
            
            self.track_cache[cache_key] = (track_details, video["id"])
            return track_details, video["id"]
            
        except Exception as e:
            LOGGER.error(f"Spotify track error: {str(e)}")
            raise Exception(f"Failed to process Spotify track: {str(e)}")

    async def playlist(self, url):
        """Get playlist tracks from Spotify"""
        if not self.spotify:
            raise Exception("Spotify client not initialized")
            
        cache_key = f"playlist_{url}"
        if cache_key in self.playlist_cache:
            return self.playlist_cache[cache_key]

        await self._rate_limit()
        
        try:
            playlist = self.spotify.playlist(url)
            if not playlist:
                raise Exception("Playlist not found")
                
            results = []
            for item in playlist["tracks"]["items"]:
                track = item["track"]
                if not track:
                    continue
                    
                artists = ", ".join(
                    artist["name"] 
                    for artist in track["artists"] 
                    if artist["name"] != "Various Artists"
                )
                results.append(f"{track['name']} {artists}")
            
            self.playlist_cache[cache_key] = (results, playlist["id"])
            return results, playlist["id"]
            
        except Exception as e:
            LOGGER.error(f"Spotify playlist error: {str(e)}")
            raise Exception(f"Failed to process playlist: {str(e)}")

    # Similar optimized implementations for album() and artist() methods
    # ...
