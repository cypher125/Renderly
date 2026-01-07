import time
import httpx
from django.conf import settings
from google.cloud import storage


class HeyGenService:
    def __init__(self):
        self.base_v1 = "https://api.heygen.com/v1"
        self.base_v2 = "https://api.heygen.com/v2"
        self.base_upload = "https://upload.heygen.com/v1"
        self._client = httpx.Client(timeout=120)

    @staticmethod
    def gcs_to_public_url(gcs_uri):
        """Convert GCS URI to public URL"""
        uri = gcs_uri.replace("gs://", "")
        parts = uri.split("/", 1)
        if len(parts) == 1:
            return f"https://storage.googleapis.com/{parts[0]}"
        return f"https://storage.googleapis.com/{parts[0]}/{parts[1]}"

    def _headers(self):
        """Return standard headers for HeyGen API calls"""
        return {
            "X-Api-Key": settings.HEYGEN_API_KEY or "",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    @staticmethod
    def _extract_asset_id(data: dict):
        """Extract asset_id from various response formats"""
        if not isinstance(data, dict):
            return None
        
        # Direct keys
        if "asset_id" in data:
            return data.get("asset_id")
        if "video_asset_id" in data:
            return data.get("video_asset_id")
        
        # Check nested data object
        d = data.get("data") or {}
        if isinstance(d, dict):
            if "asset_id" in d:
                return d.get("asset_id")
            if "video_asset_id" in d:
                return d.get("video_asset_id")
            if "id" in d:
                return d.get("id")
        
        # Check nested asset object
        a = d.get("asset") if isinstance(d, dict) else None
        if isinstance(a, dict):
            return a.get("asset_id") or a.get("id")
        
        return None

    @staticmethod
    def _parse_gs(gcs_uri: str):
        """Parse GCS URI into bucket and key"""
        assert gcs_uri.startswith("gs://")
        without = gcs_uri[5:]
        parts = without.split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""
        return bucket, key

    def generate_signed_url(self, gcs_uri: str, expiration_seconds: int = 3600) -> str:
        """Generate a signed URL for a GCS object"""
        bucket, key = self._parse_gs(gcs_uri)
        
        if settings.GCP_SERVICE_ACCOUNT_FILE:
            client = storage.Client.from_service_account_json(settings.GCP_SERVICE_ACCOUNT_FILE)
        else:
            client = storage.Client()
        
        blob = client.bucket(bucket).blob(key)
        return blob.generate_signed_url(expiration=expiration_seconds, method="GET")

    def make_fetchable_url(self, gcs_uri: str) -> str:
        """
        Convert GCS URI to a fetchable URL.
        First tries public URL, falls back to signed URL if needed.
        """
        public = self.gcs_to_public_url(gcs_uri)
        
        # Check if public URL is accessible
        try:
            r = self._client.head(public, timeout=15)
            if r.status_code == 200:
                return public
        except Exception:
            pass
        
        # Fall back to signed URL
        return self.generate_signed_url(gcs_uri)

    def upload_video_asset(self, video_url: str) -> str:
        """
        Upload video to HeyGen and return asset_id.
        HeyGen expects RAW BINARY data in request body, NOT multipart/form-data!
        """
        import requests
        
        url = f"{self.base_upload}/asset"
        
        # Download the video content first
        print(f"Downloading video from: {video_url}")
        with self._client.stream("GET", video_url, timeout=120) as r:
            r.raise_for_status()
            content = r.read()
        
        print(f"Video downloaded successfully. Size: {len(content)} bytes")
        
        # Validate API key
        api_key = settings.HEYGEN_API_KEY or ""
        if not api_key:
            raise RuntimeError("HEYGEN_API_KEY is not set in Django settings")
        
        print(f"Using API key: {api_key[:10]}...{api_key[-4:]}")
        
        # Upload as RAW BINARY data (not multipart!)
        print("Uploading as raw binary data...")
        
        # Headers for RAW binary upload
        headers = {
            "X-Api-Key": api_key,
            "Content-Type": "video/mp4",  # MIME type of the file
            "accept": "application/json",
        }
        
        try:
            # Send raw binary data directly in request body
            response = requests.post(url, headers=headers, data=content, timeout=120)
            
            # Log response details
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
            
            # Check status
            if response.status_code == 200:
                data = response.json()
                
                asset_id = self._extract_asset_id(data)
                if not asset_id:
                    raise RuntimeError(f"HeyGen upload returned success but no asset_id: {data}")
                
                print(f"✅ Upload successful! Asset ID: {asset_id}")
                return asset_id
            
            elif response.status_code == 401:
                error_msg = (
                    f"❌ Authentication failed (401). "
                    f"Please check your HEYGEN_API_KEY. "
                    f"Response: {response.text}"
                )
                print(error_msg)
                raise RuntimeError(error_msg)
            
            elif response.status_code == 400:
                error_msg = f"❌ Bad request (400). Response: {response.text}"
                print(error_msg)
                raise RuntimeError(error_msg)
            
            else:
                error_msg = f"❌ Upload failed with status {response.status_code}: {response.text}"
                print(error_msg)
                raise RuntimeError(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"❌ Request failed: {str(e)}"
            print(error_msg)
            raise RuntimeError(error_msg)

    def generate_avatar_video(
        self,
        avatar_id: str,
        voice_id: str,
        script: str,
        video_asset_id: str,
        avatar_scale: float = 1.0,
        avatar_x: float = 0.0,
        avatar_y: float = 0.0,
    ) -> str:
        """
        Generate avatar video with custom background video.
        Returns video_id for status polling.
        """
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
                        "speed": 1.0,
                    },
                    "background": {
                        "type": "video",
                        "video_asset_id": video_asset_id,
                        "play_style": "loop",
                    },
                }
            ],
            "dimension": {"width": 720, "height": 1280},
        }
        
        # Use the correct endpoint (no trailing slash)
        url = f"{self.base_v2}/video/generate"
        
        last_error = None
        
        for attempt in range(3):
            try:
                print(f"Attempting video generation (attempt {attempt + 1})")
                
                res = self._client.post(
                    url, 
                    json=payload, 
                    headers=self._headers(), 
                    timeout=120
                )
                res.raise_for_status()
                data = res.json()
                
                print(f"Generation response: {data}")
                
                # Extract video_id
                video_id = (data.get("data") or {}).get("video_id") or data.get("video_id")
                
                if not video_id:
                    print(f"No video_id in response")
                    raise RuntimeError("No video_id in response")
                
                print(f"Video generation started! Video ID: {video_id}")
                return video_id
                
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else None
                
                # Retry on temporary errors
                if status in (502, 429):
                    wait_time = 2 * (attempt + 1)
                    print(f"Got {status}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                # Log and raise for other errors
                body = e.response.text if e.response is not None else str(e)
                print(f"Request failed with {status}: {body}")
                last_error = e
                break
                
            except httpx.RequestError as e:
                print(f"Request error: {str(e)}, retrying...")
                last_error = e
                time.sleep(2 * (attempt + 1))
                continue
        
        # All attempts failed
        if last_error is not None:
            if isinstance(last_error, httpx.HTTPStatusError):
                resp = last_error.response
                status = resp.status_code if resp is not None else "unknown"
                body = resp.text if resp is not None else str(last_error)
                raise RuntimeError(f"HeyGen generate failed: {status} {body}")
            raise RuntimeError(f"HeyGen generate failed: {str(last_error)}")
        
        raise RuntimeError("HeyGen generate failed with unknown error")

    def poll_video_status(
        self, 
        video_id: str, 
        max_retries: int = 120,  # Increased from 60 to 120 (20 minutes)
        interval: int = 10
    ) -> str:
        """
        Poll HeyGen for video generation status.
        Returns the final video URL when completed.
        """
        url = f"{self.base_v1}/video_status.get"
        
        print(f"Polling video status for video_id: {video_id}")
        print(f"Will check every {interval}s for up to {max_retries * interval}s (~{max_retries * interval / 60:.1f} minutes)")
        
        for retry in range(max_retries):
            try:
                # Increase timeout for status check requests
                res = self._client.get(
                    url, 
                    params={"video_id": video_id}, 
                    headers=self._headers(),
                    timeout=30  # Increased from default
                )
                res.raise_for_status()
                data = res.json()
                
                # Extract status
                status_val = (data.get("data") or {}).get("status") or data.get("status")
                
                # Calculate progress percentage
                progress = int((retry + 1) / max_retries * 100)
                print(f"[{progress:3d}%] Status check {retry + 1}/{max_retries}: {status_val}")
                
                if status_val == "completed":
                    # Extract video URL
                    final_url = (data.get("data") or {}).get("video_url") or data.get("video_url")
                    
                    if not final_url:
                        raise RuntimeError("HeyGen final video_url not found in response")
                    
                    print(f"✅ Video generation completed! URL: {final_url}")
                    return final_url
                
                if status_val == "failed":
                    error_info = data.get("data", {}).get("error") or "Unknown error"
                    raise RuntimeError(f"HeyGen video failed: {error_info}")
                
                # Still processing, wait and retry
                time.sleep(interval)
                
            except httpx.ReadTimeout as e:
                print(f"⚠️  Status check timed out (retry {retry + 1}/{max_retries}), retrying...")
                # Don't count this as a failure, just retry
                time.sleep(interval)
                continue
                
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response else "unknown"
                body = e.response.text if e.response else str(e)
                print(f"⚠️  Status check failed: {status} - {body}")
                
                # If it's a temporary error, retry
                if status in (502, 503, 429):
                    print(f"Temporary error, retrying in {interval}s...")
                    time.sleep(interval)
                    continue
                else:
                    # For other errors, raise immediately
                    raise RuntimeError(f"Status check failed with {status}: {body}")
            
            except httpx.RequestError as e:
                print(f"⚠️  Network error: {str(e)}, retrying...")
                time.sleep(interval)
                continue
        
        # Timeout - but video might still be processing
        error_msg = (
            f"⏱️  Polling timed out after {max_retries * interval}s (~{max_retries * interval / 60:.1f} minutes). "
            f"Video might still be processing on HeyGen. "
            f"Check your HeyGen dashboard or try fetching status again with video_id: {video_id}"
        )
        raise TimeoutError(error_msg)