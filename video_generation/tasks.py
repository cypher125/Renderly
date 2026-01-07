from celery import shared_task
from django.utils import timezone
from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError, InterfaceError
from .models import VideoJob
from .services.veo_service import VeoService
from .services.heygen_service import HeyGenService
from .services.merge_service import merge_scene_urls_to_gcs
import random

@shared_task(queue='renderly', bind=True, autoretry_for=(OperationalError, InterfaceError), retry_kwargs={'max_retries': 3, 'countdown': 5})
def process_video_job(self, job_id):
    connection.close()
    job = VideoJob.objects.get(id=job_id)
    try:
        job.status = 'processing_veo'
        job.progress = 10
        job.save()
        veo = VeoService()
        hey = HeyGenService()
        prompts = []
        for s in job.scenes_data:
            prompts.append(f"{job.product_title} | {s.get('visual_description')} | {s.get('camera_movement')} | {s.get('mood')}")
        storage_base = f"gs://{settings.GCS_BUCKET}/{job.product_id or job.id}/{job.created_at.strftime('%Y-%m-%d')}/"
        scene1_prefix = f"{storage_base}scene_1/"
        base_result = veo.generate_base_video(prompts[0], job.image_url, scene1_prefix)
        job.progress = 20
        job.save()
        connection.close()
        scene1_uri = veo.poll_operation(base_result['name'], expected_storage_uri=scene1_prefix)
        job.progress = 30
        job.save()
        scene_uris = [scene1_uri]
        for i in range(1, len(prompts)):
            pfx = f"{storage_base}scene_{i+1}/"
            r = veo.generate_base_video(prompts[i], job.image_url, pfx)
            job.progress = 20 + (i * 10)
            job.save()
            connection.close()
            u = veo.poll_operation(r['name'], expected_storage_uri=pfx)
            scene_uris.append(u)
        scene_urls = [hey.make_fetchable_url(u) for u in scene_uris]
        target_gcs = f"gs://{settings.GCS_BUCKET}/{job.product_id or job.id}/merged/final.mp4"
        connection.close()
        final_veo_uri = merge_scene_urls_to_gcs(scene_urls, target_gcs)
        job.veo_video_gcs_uri = final_veo_uri
        job.veo_video_url = hey.make_fetchable_url(final_veo_uri)
        job.progress = 60
        job.status = 'processing_heygen'
        job.save()
        connection.close()
        asset_id = hey.upload_video_asset(job.veo_video_url)
        job.heygen_asset_id = asset_id
        job.progress = 70
        job.save()
        connection.close()
        video_id = hey.generate_avatar_video(job.avatar_id, job.voice_id, job.avatar_script, asset_id, job.avatar_scale, job.avatar_x, job.avatar_y)
        job.heygen_video_id = video_id
        job.progress = 80
        job.save()
        connection.close()
        final_url = hey.poll_video_status(video_id)
        connection.close()
        job = VideoJob.objects.get(id=job_id)
        if settings.BG_MUSIC_URLS:
            try:
                from .services.merge_service import add_background_music_to_video
            except ImportError:
                add_background_music_to_video = None
            if add_background_music_to_video:
                music_url = random.choice(settings.BG_MUSIC_URLS)
                target_music_gcs = f"gs://{settings.GCS_BUCKET}/{job.product_id or job.id}/final/with_music.mp4"
                try:
                    mixed_gcs_uri = add_background_music_to_video(final_url, music_url, target_music_gcs, music_volume=settings.BG_MUSIC_VOLUME)
                    job.final_video_url = hey.make_fetchable_url(mixed_gcs_uri)
                except Exception:
                    job.final_video_url = final_url
            else:
                job.final_video_url = final_url
        else:
            job.final_video_url = final_url
        job.status = 'completed'
        job.progress = 100
        job.completed_at = timezone.now()
        created = job.created_at
        if timezone.is_naive(created):
            created = timezone.make_aware(created, timezone.get_current_timezone())
        job.processing_time_seconds = int((timezone.now() - created).total_seconds())
        job.credits_used = 1
        job.save()
    except Exception as e:
        connection.close()
        job = VideoJob.objects.get(id=job_id)
        job.status = 'failed'
        job.error_message = str(e)
        job.save()
