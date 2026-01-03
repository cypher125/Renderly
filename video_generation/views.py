from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from .serializers import VideoGenerationRequestSerializer, VideoJobSerializer
from .models import VideoJob
from .tasks import process_video_job
from django.conf import settings
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes
from django.utils import timezone
import redis
import threading

class VideoGenerationViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = VideoJobSerializer
    queryset = VideoJob.objects.all()

    @extend_schema(
        tags=['Video Generation'],
        summary='Start video generation job',
        description='Creates a new job and starts background processing to generate a 24-second Veo video and overlay a HeyGen avatar.',
        request=VideoGenerationRequestSerializer,
        responses={
            202: OpenApiResponse(description='Job accepted and started'),
            400: OpenApiResponse(description='Validation error'),
            401: OpenApiResponse(description='Unauthorized'),
        },
        operation_id='video_generate',
        examples=[
            OpenApiExample(
                'Example Request',
                value={
                    "product_title": "Premium Wireless Headphones",
                    "scenes": [
                        {"visual_description": "Desk scene", "camera_movement": "slow 360", "mood": "premium", "duration": 8},
                        {"visual_description": "Close-up controls", "camera_movement": "zoom in", "mood": "sophisticated", "duration": 8},
                        {"visual_description": "Comfort wear", "camera_movement": "gentle pan", "mood": "comfortable", "duration": 8},
                    ],
                    "image_url": "https://cdn.example.com/headphones.jpg",
                    "avatar_id": "josh_lite3_20230714",
                    "voice_id": "d7bbcdd6964c47bdaae26decade4a933",
                    "avatar_script": "Introducing our revolutionary wireless headphones...",
                    "avatar_position": {"scale": 0.8, "x": 0.7, "y": 0.8}
                },
            )
        ],
    )
    @action(detail=False, methods=['post'])
    def generate(self, request):
        serializer = VideoGenerationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        pos = data.get('avatar_position', {})
        job = VideoJob.objects.create(
            user=request.user,
            product_id=data.get('product_id'),
            product_title=data['product_title'],
            scenes_data=data['scenes'],
            avatar_script=data['avatar_script'],
            avatar_id=data['avatar_id'],
            voice_id=data['voice_id'],
            image_url=data['image_url'],
            avatar_scale=pos.get('scale', 0.8),
            avatar_x=pos.get('x', 0.7),
            avatar_y=pos.get('y', 0.8),
            status='pending'
        )
        try:
            broker_ok = True
            try:
                r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
                r.ping()
            except Exception:
                broker_ok = False
            use_inline = getattr(settings, 'RUN_TASK_INLINE', False) or not broker_ok
            if use_inline:
                threading.Thread(target=lambda: process_video_job.apply(args=[str(job.id)])).start()
            else:
                process_video_job.apply_async(args=[str(job.id)], queue='renderly')
        except Exception:
            threading.Thread(target=lambda: process_video_job.apply(args=[str(job.id)])).start()
        return Response({
            'job_id': str(job.id),
            'status': 'pending',
            'message': 'Video generation started',
            'estimated_time_seconds': len(data['scenes']) * 120
        }, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        tags=['Jobs'],
        summary='Get job status',
        operation_id='video_get_status',
        parameters=[
            OpenApiParameter(
                name='job_id',
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description='VideoJob UUID',
                required=True,
            ),
        ],
        responses={
            200: VideoJobSerializer,
            404: OpenApiResponse(description='Job not found'),
            401: OpenApiResponse(description='Unauthorized'),
        },
    )
    @action(detail=False, methods=['get'], url_path='status/(?P<job_id>[^/.]+)')
    def get_status(self, request, job_id=None):
        try:
            job = VideoJob.objects.get(id=job_id, user=request.user)
        except VideoJob.DoesNotExist:
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = VideoJobSerializer(job)
        return Response(serializer.data)

    @extend_schema(
        tags=['Jobs'],
        summary='List jobs for current user',
        description='Returns all jobs for the authenticated user. Optional query parameter "status" filters by job status.',
        operation_id='video_list_jobs',
        parameters=[
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by status',
                required=False,
                enum=['pending','processing_veo','processing_heygen','completed','failed'],
            ),
        ],
        responses={200: VideoJobSerializer(many=True)},
        examples=[
            OpenApiExample('Filter by status', value={'status': 'completed'}, request_only=True),
        ],
    )
    @action(detail=False, methods=['get'])
    def list_jobs(self, request):
        jobs = VideoJob.objects.filter(user=request.user)
        status_filter = request.query_params.get('status')
        if status_filter:
            jobs = jobs.filter(status=status_filter)
        serializer = VideoJobSerializer(jobs, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=['System'],
        summary='Health check',
        operation_id='system_health',
        responses={
            200: OpenApiResponse(description='Health status'),
        },
    )
    @action(detail=False, methods=['get'])
    def health(self, request):
        db_status = 'connected'
        try:
            VideoJob.objects.exists()
        except Exception:
            db_status = 'error'
        redis_status = 'unknown'
        try:
            r = redis.Redis.from_url(settings.CELERY_RESULT_BACKEND)
            if r.ping():
                redis_status = 'connected'
            else:
                redis_status = 'error'
        except Exception:
            redis_status = 'error'
        return Response({
            'status': 'healthy' if db_status == 'connected' else 'degraded',
            'timestamp': timezone.now(),
            'database': db_status,
            'redis': redis_status,
        })
