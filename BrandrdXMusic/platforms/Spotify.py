import re
import time
import json
from pathlib import Path
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from youtubesearchpython.__future__ import VideosSearch
import config
from cachetools import TTLCache
from datetime import datetime, timedelta

class SpotifyAPI:
    def __init__(self):
        self.regex = r"^(https:\/\/open.spotify\.com\/)(.*)$"
        self.client_id = config.SPOTIFY_CLIENT_ID
        self.client_secret = config.SPOTIFY_CLIENT_SECRET
        
        # Initialize caches
        self.track_cache = TTLCache(maxsize=500, ttl=3600)  # 1 hour cache
        self.playlist_cache = TTLCache(maxsize=100, ttl=7200)  # 2 hour cache
        self.last_request_time = datetime.now()
        self.request_delay = 0.5  # seconds between requests
        
        # Initialize Spotify client
        if self.client_id and self.client_secret:
            self.client_credentials_manager = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            self.spotify = spotipy.Spotify(
                client_credentials_manager=self.client_credentials_manager,
                retries=3,
                status_forcelist=[429, 500, 502, 503, 504]
            )
        else:
            self.spotify = None

    async def _rate_limit(self):
        """Enforce rate limiting between requests"""
        elapsed = (datetime.now() - self.last_request_time).total_seconds()
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = datetime.now()

    async def valid(self, link: str):
        return bool(re.search(self.regex, link))

    async def track(self, link: str):
        cache_key = f"track_{link}"
        if cache_key in self.track_cache:
            return self.track_cache[cache_key]

        await self._rate_limit()
        
        try:
            track = self.spotify.track(link)
            info = track["name"]
            for artist in track["artists"]:
                if artist["name"] != "Various Artists":
                    info += f' {artist["name"]}'

            # Search YouTube
            results = VideosSearch(info, limit=1)
            video = (await results.next())["result"][0]
            
            track_details = {
                "title": video["title"],
                "link": video["link"],
                "vidid": video["id"],
                "duration_min": video["duration"],
                "thumb": video["thumbnails"][0]["url"].split("?")[0],
            }
            
            self.track_cache[cache_key] = (track_details, video["id"])
            return track_details, video["id"]
            
        except Exception as e:
            print(f"Spotify track error: {e}")
            raise

    async def playlist(self, url):
        cache_key = f"playlist_{url}"
        if cache_key in self.playlist_cache:
            return self.playlist_cache[cache_key]

        await self._rate_limit()
        
        try:
            playlist = self.spotify.playlist(url)
            results = []
            
            for item in playlist["tracks"]["items"]:
                track = item["track"]
                info = track["name"]
                for artist in track["artists"]:
                    if artist["name"] != "Various Artists":
                        info += f' {artist["name"]}'
                results.append(info)
            
            self.playlist_cache[cache_key] = (results, playlist["id"])
            return results, playlist["id"]
            
        except Exception as e:
            print(f"Spotify playlist error: {e}")
            raise

    async def album(self, url):
        cache_key = f"album_{url}"
        if cache_key in self.playlist_cache:
            return self.playlist_cache[cache_key]

        await self._rate_limit()
        
        try:
            album = self.spotify.album(url)
            results = []
            
            for item in album["tracks"]["items"]:
                info = item["name"]
                for artist in item["artists"]:
                    if artist["name"] != "Various Artists":
                        info += f' {artist["name"]}'
                results.append(info)
            
            self.playlist_cache[cache_key] = (results, album["id"])
            return results, album["id"]
            
        except Exception as e:
            print(f"Spotify album error: {e}")
            raise

    async def artist(self, url):
        cache_key = f"artist_{url}"
        if cache_key in self.playlist_cache:
            return self.playlist_cache[cache_key]

        await self._rate_limit()
        
        try:
            artist_top_tracks = self.spotify.artist_top_tracks(url)
            results = []
            
            for item in artist_top_tracks["tracks"]:
                info = item["name"]
                for artist in item["artists"]:
                    if artist["name"] != "Various Artists":
                        info += f' {artist["name"]}'
                results.append(info)
            
            self.playlist_cache[cache_key] = (results, artist_top_tracks["tracks"][0]["artists"][0]["id"])
            return results, artist_top_tracks["tracks"][0]["artists"][0]["id"]
            
        except Exception as e:
            print(f"Spotify artist error: {e}")
            raise
