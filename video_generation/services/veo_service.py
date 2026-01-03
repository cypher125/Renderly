import base64
import httpx
from django.conf import settings
from .gcp_auth import GCPAuthManager

class VeoService:
    def __init__(self):
        self.project_id = settings.GCP_PROJECT_ID
        self.location = "us-central1"
        self.model = "veo-3.1-generate-preview"
        self.base_url = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{self.model}"
        self._client = httpx.Client(timeout=120)
        self._auth = GCPAuthManager()

    def _image_to_b64(self, image_url: str) -> str:
        r = self._client.get(image_url, timeout=60)
        r.raise_for_status()
        return base64.b64encode(r.content).decode("utf-8")

    def _headers(self):
        h = {"Content-Type": "application/json"}
        h.update(self._auth.get_authorization_header())
        return h

    def generate_base_video(self, prompt, image_url, storage_uri):
        image_b64 = self._image_to_b64(image_url)
        body = {
            "instances": [
                {
                    "prompt": prompt,
                    "durationSeconds": 8,
                    "aspectRatio": "9:16",
                    "resolution": "720p",
                    "sampleCount": 1,
                    "resizeMode": "crop",
                    "image": {"bytesBase64Encoded": image_b64},
                }
            ],
            "parameters": {"storageUri": storage_uri},
        }
        url = f"{self.base_url}:predictLongRunning"
        res = self._client.post(url, json=body, headers=self._headers())
        res.raise_for_status()
        return res.json()

    def extend_video(self, video_gcs_uri, prompt, image_url, storage_uri):
        image_b64 = self._image_to_b64(image_url)
        body = {
            "instances": [
                {
                    "prompt": prompt,
                    "durationSeconds": 8,
                    "aspectRatio": "9:16",
                    "resolution": "720p",
                    "sampleCount": 1,
                    "resizeMode": "crop",
                    "video": {"gcsUri": video_gcs_uri},
                    "image": {"bytesBase64Encoded": image_b64},
                }
            ],
            "parameters": {"storageUri": storage_uri},
        }
        url = f"{self.base_url}:predictLongRunning"
        res = self._client.post(url, json=body, headers=self._headers())
        res.raise_for_status()
        return res.json()

    def poll_operation(self, operation_name, max_retries: int = 60):
        url = f"{self.base_url}:fetchPredictOperation"
        name = operation_name if isinstance(operation_name, str) else operation_name.get("name")
        for _ in range(max_retries):
            res = self._client.get(url, params={"name": name}, headers=self._headers())
            res.raise_for_status()
            data = res.json()
            done = data.get("done")
            if done:
                outputs = data.get("response", {}).get("predictions") or []
                for out in outputs:
                    uri = out.get("gcsUri") or out.get("storageUri")
                    if uri:
                        return uri
                raise RuntimeError("Operation completed without gcsUri in response")
        raise TimeoutError("Veo operation polling timed out")
