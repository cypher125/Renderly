import time
import httpx
from django.conf import settings

class HeyGenService:
    def __init__(self):
        self.base_v1 = "https://api.heygen.com/v1"
        self.base_v2 = "https://api.heygen.com/v2"
        self._client = httpx.Client(timeout=120)

    @staticmethod
    def gcs_to_public_url(gcs_uri):
        uri = gcs_uri.replace("gs://", "")
        parts = uri.split("/", 1)
        if len(parts) == 1:
            return f"https://storage.googleapis.com/{parts[0]}"
        return f"https://storage.googleapis.com/{parts[0]}/{parts[1]}"

    def _headers(self):
        return {
            "X-Api-Key": settings.HEYGEN_API_KEY or "",
            "Content-Type": "application/json",
        }

    def upload_video_asset(self, video_url: str) -> str:
        url = f"{self.base_v1}/asset"
        res = self._client.post(url, json={"url": video_url}, headers=self._headers())
        res.raise_for_status()
        data = res.json()
        asset_id = (data.get("data") or {}).get("asset_id") or data.get("asset_id")
        if not asset_id:
            raise RuntimeError("HeyGen asset_id not found in response")
        return asset_id

    def generate_avatar_video(
        self,
        avatar_id: str,
        voice_id: str,
        script: str,
        video_asset_id: str,
        avatar_scale: float,
        avatar_x: float,
        avatar_y: float,
    ) -> str:
        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal",
                        "scale": avatar_scale,
                        "offset": {"x": avatar_x, "y": avatar_y},
                        "matting": True,
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script,
                        "voice_id": voice_id,
                    },
                    "background": {
                        "type": "video",
                        "video_asset_id": video_asset_id,
                        "play_style": "full_video",
                    },
                }
            ],
            "dimension": {"width": 720, "height": 1280},
            "aspect_ratio": "9:16",
        }
        url = f"{self.base_v2}/video/generate"
        res = self._client.post(url, json=payload, headers=self._headers())
        res.raise_for_status()
        data = res.json()
        video_id = (data.get("data") or {}).get("video_id") or data.get("video_id")
        if not video_id:
            raise RuntimeError("HeyGen video_id not found in response")
        return video_id

    def poll_video_status(self, video_id: str, max_retries: int = 60, interval: int = 10) -> str:
        url = f"{self.base_v1}/video_status.get"
        for _ in range(max_retries):
            res = self._client.get(url, params={"video_id": video_id}, headers=self._headers())
            res.raise_for_status()
            data = res.json()
            status_val = (data.get("data") or {}).get("status") or data.get("status")
            if status_val == "completed":
                final_url = (data.get("data") or {}).get("video_url") or data.get("video_url")
                if not final_url:
                    raise RuntimeError("HeyGen final video_url not found in response")
                return final_url
            if status_val == "failed":
                raise RuntimeError(f"HeyGen video failed: {data}")
            time.sleep(interval)
        raise TimeoutError("HeyGen video generation timed out")
