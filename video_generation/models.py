from django.conf import settings
from django.db import models
import uuid

class VideoJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'pending'),
        ('processing_veo', 'processing_veo'),
        ('processing_heygen', 'processing_heygen'),
        ('completed', 'completed'),
        ('failed', 'failed'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product_id = models.CharField(max_length=255, blank=True, null=True)
    product_title = models.CharField(max_length=500)
    scenes_data = models.JSONField()
    avatar_script = models.TextField()
    avatar_id = models.CharField(max_length=255)
    voice_id = models.CharField(max_length=255)
    image_url = models.URLField()
    avatar_scale = models.FloatField(default=0.8)
    avatar_x = models.FloatField(default=0.7)
    avatar_y = models.FloatField(default=0.8)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    veo_video_gcs_uri = models.CharField(max_length=1024, blank=True)
    veo_video_url = models.URLField(blank=True)
    heygen_video_id = models.CharField(max_length=255, blank=True)
    heygen_asset_id = models.CharField(max_length=255, blank=True)
    final_video_url = models.URLField(blank=True, max_length=2048)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    processing_time_seconds = models.IntegerField(blank=True, null=True)
    credits_used = models.IntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['status']),
        ]
        ordering = ['-created_at']
