import base64
import mimetypes
import io
import time
import httpx
from django.conf import settings
from .gcp_auth import GCPAuthManager
from PIL import Image
from google.cloud import storage

class VeoService:
    def __init__(self):
        self.project_id = settings.GCP_PROJECT_ID
        self.location = getattr(settings, 'VEO_LOCATION', 'us-central1')
        self.model = getattr(settings, 'VEO_MODEL_NAME', 'veo-3.1')
        self.base_url = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/publishers/google/models/{self.model}"
        self._client = httpx.Client(timeout=120)
        self._auth = GCPAuthManager()

    def _guess_mime(self, url: str) -> str:
        mime, _ = mimetypes.guess_type(url)
        return mime or "image/jpeg"

    def _image_to_b64_with_mime(self, image_url: str):
        r = self._client.get(image_url, timeout=60)
        r.raise_for_status()
        content = r.content
        ct = r.headers.get("Content-Type", "") or self._guess_mime(image_url)
        if "image/webp" in ct:
            img = Image.open(io.BytesIO(content)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            content = buf.getvalue()
            ct = "image/jpeg"
        b64 = base64.b64encode(content).decode("utf-8")
        return b64, ct

    def _headers(self):
        h = {"Content-Type": "application/json", "x-goog-user-project": self.project_id}
        h.update(self._auth.get_authorization_header())
        return h

    def generate_base_video(self, prompt, image_url, storage_uri):
        image_b64, mime = self._image_to_b64_with_mime(image_url)
        body = {
            "instances": [
                {
                    "prompt": prompt,
                    "referenceImages": [
                        {
                            "image": {"bytesBase64Encoded": image_b64, "mimeType": mime},
                            "referenceType": "asset",
                        }
                    ],
                }
            ],
            "parameters": {
                "durationSeconds": 8,
                "storageUri": storage_uri,
                "sampleCount": 1,
                "resolution": "720p",
                "aspectRatio": "9:16",
            },
        }
        url = f"{self.base_url}:predictLongRunning"
        try:
            res = self._client.post(url, json=body, headers=self._headers())
            res.raise_for_status()
            return res.json()
        except httpx.HTTPStatusError as e:
            # Fallback to text-only prompt if project isn't allowlisted for references
            err_json = {}
            try:
                err_json = e.response.json()
            except Exception:
                pass
            msg = ((err_json or {}).get("error", {}) or {}).get("message", "")
            status = ((err_json or {}).get("error", {}) or {}).get("status", "")
            if "allowlisted" in msg or status == "FAILED_PRECONDITION":
                text_only_body = {
                    "instances": [{"prompt": prompt}],
                    "parameters": {
                        "durationSeconds": 8,
                        "storageUri": storage_uri,
                        "sampleCount": 1,
                        "resolution": "720p",
                        "aspectRatio": "9:16",
                    },
                }
                res2 = self._client.post(url, json=text_only_body, headers=self._headers())
                res2.raise_for_status()
                return res2.json()
            detail = e.response.text if e.response is not None else str(e)
            raise RuntimeError(f"Veo generate_base_video failed: {detail}")

    def extend_video(self, video_gcs_uri, prompt, image_url, storage_uri):
        body = {
            "instances": [
                {
                    "prompt": prompt,
                    "video": {"gcsUri": video_gcs_uri, "mimeType": "video/mp4"},
                }
            ],
            "parameters": {
                "durationSeconds": 8,
                "storageUri": storage_uri,
                "sampleCount": 1,
                "resolution": "720p",
            },
        }
        url = f"{self.base_url}:predictLongRunning"
        try:
            res = self._client.post(url, json=body, headers=self._headers())
            res.raise_for_status()
            return res.json()
        except httpx.HTTPStatusError as e:
            detail = e.response.text if e.response is not None else str(e)
            raise RuntimeError(f"Veo extend_video failed: {detail}")

    def _parse_gs_uri(self, uri: str):
        if not uri.startswith("gs://"):
            return None, None
        without = uri[len("gs://"):]
        parts = without.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        return bucket, prefix

    def _wait_for_gcs_output(self, expected_storage_uri: str, max_retries: int = 120, poll_interval_seconds: int = 5):
        bucket_name, prefix = self._parse_gs_uri(expected_storage_uri)
        if not bucket_name or not prefix:
            return None
        try:
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            for _ in range(max_retries):
                blobs = list(bucket.list_blobs(prefix=prefix))
                mp4s = [b for b in blobs if b.name.endswith(".mp4")]
                if mp4s:
                    return f"gs://{bucket_name}/{mp4s[0].name}"
                time.sleep(poll_interval_seconds)
        except Exception:
            pass
        return None

    def _wait_for_public_gcs_output(self, expected_storage_uri: str, sample_index: int = 0, op_id: str = None):
        bucket, prefix = self._parse_gs_uri(expected_storage_uri)
        if not bucket or not prefix:
            return None
        candidates = []
        if op_id:
            candidates.append(f"{prefix}{op_id}/sample_{sample_index}.mp4")
        candidates.append(f"{prefix}sample_{sample_index}.mp4")
        for object_path in candidates:
            url = f"https://storage.googleapis.com/{bucket}/{object_path}"
            try:
                r = self._client.head(url, timeout=15)
                if r.status_code == 200:
                    return f"gs://{bucket}/{object_path}"
            except Exception:
                continue
        return None

    def _list_public_gcs_mp4(self, expected_storage_uri: str):
        bucket, prefix = self._parse_gs_uri(expected_storage_uri)
        if not bucket or not prefix:
            return None
        api_url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o"
        params = {"prefix": prefix}
        try:
            r = self._client.get(api_url, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                for item in data.get("items", []):
                    name = item.get("name", "")
                    if name.endswith(".mp4"):
                        return f"gs://{bucket}/{name}"
        except Exception:
            pass
        return None

    def poll_operation(self, operation_name, expected_storage_uri: str = None, max_retries: int = 120, poll_interval_seconds: int = 5):
        name = operation_name if isinstance(operation_name, str) else operation_name.get("name")
        op_id = None
        if isinstance(name, str):
            try:
                op_id = name.split("/")[-1]
            except Exception:
                op_id = None
        urls = []
        if isinstance(name, str) and name.startswith("projects/"):
            urls = [f"https://{self.location}-aiplatform.googleapis.com/v1/{name}"]
        else:
            op = op_id or name
            general = f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{self.project_id}/locations/{self.location}/operations/{op}"
            model_ops = f"{self.base_url}/operations/{op}"
            urls = [general, model_ops]
        for _ in range(max_retries):
            got_data = False
            data = None
            last_status = None
            last_body = None
            for u in urls:
                try:
                    res = self._client.get(u, headers=self._headers())
                    res.raise_for_status()
                    data = res.json()
                    got_data = True
                    break
                except httpx.HTTPStatusError as e:
                    last_status = e.response.status_code if e.response is not None else None
                    last_body = e.response.text if e.response is not None else str(e)
                    if last_status == 401:
                        raise RuntimeError(f"Veo poll_operation authentication failed: {last_body}")
                    continue
            if not got_data:
                if expected_storage_uri:
                    public_fb = self._wait_for_public_gcs_output(expected_storage_uri, op_id=op_id)
                    if public_fb:
                        return public_fb
                    list_fb = self._list_public_gcs_mp4(expected_storage_uri)
                    if list_fb:
                        return list_fb
                time.sleep(poll_interval_seconds)
                continue
            if data.get("done"):
                resp = data.get("response", {}) or {}
                videos = resp.get("videos") or []
                for v in videos:
                    uri = v.get("gcsUri") or v.get("storageUri")
                    if uri:
                        return uri
                preds = resp.get("predictions") or []
                for p in preds:
                    uri = p.get("gcsUri") or p.get("storageUri")
                    if uri:
                        return uri
                if expected_storage_uri:
                    fallback = self._wait_for_gcs_output(expected_storage_uri, max_retries=12, poll_interval_seconds=poll_interval_seconds)
                    if fallback:
                        return fallback
                    public_fb = self._wait_for_public_gcs_output(expected_storage_uri, op_id=op_id)
                    if public_fb:
                        return public_fb
                    list_fb = self._list_public_gcs_mp4(expected_storage_uri)
                    if list_fb:
                        return list_fb
            else:
                if expected_storage_uri:
                    public_fb = self._wait_for_public_gcs_output(expected_storage_uri, op_id=op_id)
                    if public_fb:
                        return public_fb
                    list_fb = self._list_public_gcs_mp4(expected_storage_uri)
                    if list_fb:
                        return list_fb
            time.sleep(poll_interval_seconds)
        if expected_storage_uri:
            fallback = self._wait_for_gcs_output(expected_storage_uri, max_retries=12, poll_interval_seconds=poll_interval_seconds)
            if fallback:
                return fallback
            public_fb = self._wait_for_public_gcs_output(expected_storage_uri, op_id=op_id)
            if public_fb:
                return public_fb
            list_fb = self._list_public_gcs_mp4(expected_storage_uri)
            if list_fb:
                return list_fb
        raise TimeoutError("Veo operation polling timed out")
