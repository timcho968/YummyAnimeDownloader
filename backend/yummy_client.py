import httpx
from .models import AnimeSearchResult, AnimeDetail, VideoEntry


BASE_URL = "https://api.yani.tv"
HEADERS = {
    "Accept": "application/json",
    "Lang": "ru",
}


class YummyClient:
    def __init__(self, app_token: str = ""):
        self.app_token = app_token
        self.headers = {**HEADERS}
        if app_token:
            self.headers["X-Application"] = app_token

    async def search(self, query: str, limit: int = 20) -> list[AnimeSearchResult]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/anime",
                params={"q": query, "limit": limit},
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("response", data.get("data", [])):
            poster = item.get("poster", {})
            poster_url = poster.get("fullsize", "") if isinstance(poster, dict) else poster

            rating = item.get("rating", {})
            rating_val = rating.get("average", 0) if isinstance(rating, dict) else rating

            results.append(AnimeSearchResult(
                id=item.get("anime_id", item.get("id", 0)),
                name=item.get("title", item.get("name", "")),
                url=item.get("anime_url", item.get("url", "")),
                poster=poster_url,
                rating=rating_val,
                year=item.get("year"),
                type=item.get("type", {}).get("name") if isinstance(item.get("type"), dict) else item.get("type"),
                episodes_count=item.get("episodes_count"),
            ))
        return results

    async def get_anime_detail(self, anime_url: str) -> AnimeDetail:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/anime/{anime_url}",
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        anime = data.get("response", data.get("data", data))

        # Fetch videos from separate endpoint
        anime_id = anime.get("anime_id", anime.get("id", 0))
        episodes = await self.get_anime_videos(anime_id)

        poster = anime.get("poster", {})
        poster_url = poster.get("fullsize", "") if isinstance(poster, dict) else poster

        rating = anime.get("rating", {})
        rating_val = rating.get("average", 0) if isinstance(rating, dict) else rating

        return AnimeDetail(
            id=anime_id,
            name=anime.get("title", anime.get("name", "")),
            url=anime.get("anime_url", anime.get("url", "")),
            poster=poster_url,
            rating=rating_val,
            description=anime.get("description"),
            episodes=episodes,
        )

    async def get_anime_videos(self, anime_id: int) -> list[VideoEntry]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/anime/{anime_id}/videos",
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        videos = data.get("response", data.get("data", []))
        if isinstance(videos, dict):
            # If it's a dict, try to get the list from values
            for v in videos.values():
                if isinstance(v, list):
                    videos = v
                    break
            else:
                videos = []

        episodes = []
        for v in videos:
            data_block = v.get("data", {})
            episodes.append(VideoEntry(
                video_id=v.get("video_id", 0),
                iframe_url=v.get("iframe_url", ""),
                number=str(v.get("number", "")),
                dubbing=data_block.get("dubbing", "Unknown"),
                player=data_block.get("player", "Unknown"),
                player_id=data_block.get("player_id", 0),
                index=v.get("index", 0),
            ))

        episodes.sort(key=lambda e: (e.dubbing, e.index))
        return episodes
