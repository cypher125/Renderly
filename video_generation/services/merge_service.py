import os
import tempfile
import shutil
from urllib.parse import urlparse
import httpx
import ffmpeg
from google.cloud import storage
from django.conf import settings

def _download_to_temp(url: str) -> str:
    fd, path = tempfile.mkstemp(suffix='.mp4')
    os.close(fd)
    with httpx.stream('GET', url, timeout=120) as r:
        r.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return path

def _concat_with_ffmpeg(paths: list[str]) -> str:
    if shutil.which('ffmpeg') is None:
        raise RuntimeError('FFmpeg is not installed or not in PATH. Install ffmpeg to enable scene merging.')
    list_fd, list_path = tempfile.mkstemp(suffix='.txt')
    os.close(list_fd)
    with open(list_path, 'w', encoding='utf-8') as f:
        for p in paths:
            f.write(f"file '{p}'\n")
    out_fd, out_path = tempfile.mkstemp(suffix='.mp4')
    os.close(out_fd)
    (
        ffmpeg
        .input(list_path, format='concat', safe=0)
        .output(out_path, c='copy')
        .run(quiet=True, overwrite_output=True)
    )
    os.remove(list_path)
    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass
    return out_path

def _upload_to_gcs(local_path: str, gcs_uri: str) -> str:
    assert gcs_uri.startswith('gs://')
    without_scheme = gcs_uri[5:]
    bucket_name, blob_name = without_scheme.split('/', 1)
    client = storage.Client.from_service_account_json(settings.GCP_SERVICE_ACCOUNT_FILE) if settings.GCP_SERVICE_ACCOUNT_FILE else storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path, content_type='video/mp4')
    return gcs_uri

def merge_scene_urls_to_gcs(scene_urls: list[str], target_gcs_uri: str) -> str:
    temp_paths = [_download_to_temp(url) for url in scene_urls]
    merged_path = _concat_with_ffmpeg(temp_paths)
    return _upload_to_gcs(merged_path, target_gcs_uri)
