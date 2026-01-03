from rest_framework import serializers
from .models import VideoJob

class SceneSerializer(serializers.Serializer):
    visual_description = serializers.CharField(max_length=1000)
    camera_movement = serializers.CharField(max_length=500)
    mood = serializers.CharField(max_length=500)
    duration = serializers.IntegerField(default=8, min_value=4, max_value=8)
    text_overlay = serializers.CharField(max_length=500, required=False, allow_blank=True)

class AvatarPositionSerializer(serializers.Serializer):
    scale = serializers.FloatField(default=0.8, min_value=0.1, max_value=1.0)
    x = serializers.FloatField(default=0.7, min_value=-1.0, max_value=1.0)
    y = serializers.FloatField(default=0.8, min_value=-1.0, max_value=1.0)

class VideoGenerationRequestSerializer(serializers.Serializer):
    product_id = serializers.CharField(max_length=255, required=False, allow_null=True)
    product_title = serializers.CharField(max_length=500)
    scenes = serializers.ListField(child=SceneSerializer(), min_length=1, max_length=20)
    image_url = serializers.URLField()
    avatar_id = serializers.CharField(max_length=255)
    voice_id = serializers.CharField(max_length=255)
    avatar_script = serializers.CharField()
    avatar_position = AvatarPositionSerializer(required=False)
    webhook_url = serializers.URLField(required=False, allow_null=True)

class VideoJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoJob
        fields = [
            'id', 'status', 'progress', 'product_title',
            'created_at', 'updated_at', 'completed_at',
            'processing_time_seconds', 'veo_video_url',
            'final_video_url', 'error_message', 'credits_used'
        ]
        read_only_fields = fields
