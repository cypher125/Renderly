from celery import shared_task
from django.utils import timezone
from django.conf import settings
from .models import VideoJob
from .services.veo_service import VeoService
from .services.heygen_service import HeyGenService
from .services.merge_service import merge_scene_urls_to_gcs

@shared_task(queue='renderly')
def process_video_job(job_id):
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
        base_result = veo.generate_base_video(prompts[0], job.image_url, f"{storage_base}scene_1/")
        scene1_uri = veo.poll_operation(base_result['name'])
        job.progress = 30
        job.save()
        try:
            ext1_result = veo.extend_video(scene1_uri, prompts[1], job.image_url, f"{storage_base}scene_2/")
            scene2_uri = veo.poll_operation(ext1_result['name'])
            job.progress = 50
            job.save()
            ext2_result = veo.extend_video(scene2_uri, prompts[2], job.image_url, f"{storage_base}scene_3/")
            final_veo_uri = veo.poll_operation(ext2_result['name'])
        except Exception:
            # Fallback: generate independent scenes and merge them
            job.progress = 45
            job.save()
            scene_uris = [scene1_uri]
            for i in range(1, len(prompts)):
                r = veo.generate_base_video(prompts[i], job.image_url, f"{storage_base}scene_{i+1}/")
                u = veo.poll_operation(r['name'])
                scene_uris.append(u)
            scene_urls = [hey.gcs_to_public_url(u) for u in scene_uris]
            target_gcs = f"gs://{settings.GCS_BUCKET}/{job.product_id or job.id}/merged/final.mp4"
            final_veo_uri = merge_scene_urls_to_gcs(scene_urls, target_gcs)
        job.veo_video_gcs_uri = final_veo_uri
        job.veo_video_url = hey.gcs_to_public_url(final_veo_uri)
        job.progress = 60
        job.status = 'processing_heygen'
        job.save()
        asset_id = hey.upload_video_asset(job.veo_video_url)
        job.heygen_asset_id = asset_id
        job.progress = 70
        job.save()
        video_id = hey.generate_avatar_video(job.avatar_id, job.voice_id, job.avatar_script, asset_id, job.avatar_scale, job.avatar_x, job.avatar_y)
        job.heygen_video_id = video_id
        job.progress = 80
        job.save()
        final_url = hey.poll_video_status(video_id)
        job.final_video_url = final_url
        job.status = 'completed'
        job.progress = 100
        job.completed_at = timezone.now()
        job.processing_time_seconds = int((timezone.now() - job.created_at).total_seconds())
        job.credits_used = 1
        job.save()
    except Exception as e:
        job.status = 'failed'
        job.error_message = str(e)
        job.save()
