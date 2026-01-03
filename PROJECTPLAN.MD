# 🎬 COMPREHENSIVE BUILD PROMPT FOR CURSOR AI / AI CODE EDITOR

## PROJECT OVERVIEW

Build a **Django REST API** for automated video generation that combines **Google Vertex AI Veo 3** (for B-roll footage) with **HeyGen avatars** (for presenter overlay). The system generates professional product videos by:

1. Creating 24-second (or custom length) B-roll videos using Veo's video generation and extension capabilities
2. Uploading the Veo video to HeyGen as a background asset
3. Generating an avatar presenter that speaks a script with the Veo video playing behind them
4. Returning a single, merged, production-ready video URL

This API is designed to be **SaaS-ready** with user management, job tracking, background processing, and billing integration capabilities.

---

## 🎯 CORE REQUIREMENTS

### **Technology Stack**
- **Framework**: Django 4.2+ with Django REST Framework
- **Database**: PostgreSQL (production) / SQLite (development)
- **Background Tasks**: Celery with Redis as message broker
- **Authentication**: Django Token Authentication
- **External APIs**: 
  - Google Vertex AI (Veo 3.1 video generation)
  - HeyGen API v2 (avatar video generation)
- **HTTP Client**: httpx (async support)
- **Cloud Storage**: Google Cloud Storage (GCS)

### **Project Structure**
```
renderly/
├── manage.py
├── requirements.txt
├── .env
├── .gitignore
├── README.md
├── renderly/                      # Main project directory
│   ├── __init__.py
│   ├── settings.py               # Django settings
│   ├── urls.py                   # Main URL routing
│   ├── celery.py                 # Celery configuration
│   └── wsgi.py
└── video_generation/              # Main app
    ├── __init__.py
    ├── models.py                 # Database models
    ├── serializers.py            # DRF serializers
    ├── views.py                  # API views/viewsets
    ├── urls.py                   # App URL routing
    ├── tasks.py                  # Celery background tasks
    ├── admin.py                  # Django admin configuration
    ├── apps.py
    ├── tests.py
    ├── migrations/
    └── services/                 # Business logic services
        ├── __init__.py
        ├── gcp_auth.py          # GCP authentication manager
        ├── veo_service.py       # Vertex AI Veo integration
        └── heygen_service.py    # HeyGen API integration
```

---

## 📊 DATABASE SCHEMA

### **VideoJob Model** (video_generation/models.py)

This model tracks every video generation job with complete metadata.

**Fields:**
- `id`: UUIDField (primary key, auto-generated)
- `user`: ForeignKey to Django User (who requested the video)
- `product_id`: CharField (optional, customer's internal product ID)
- `product_title`: CharField (product/content title, max 500 chars)
- `scenes_data`: JSONField (array of scene objects with prompts, camera movements, moods)
- `avatar_script`: TextField (text for avatar to speak, 24-30 seconds worth)
- `avatar_id`: CharField (HeyGen avatar identifier)
- `voice_id`: CharField (HeyGen voice identifier)
- `image_url`: URLField (product image URL for Veo reference)
- `avatar_scale`: FloatField (avatar size, 0.1-1.0, default 0.8)
- `avatar_x`: FloatField (horizontal position, -1.0 to 1.0, default 0.7)
- `avatar_y`: FloatField (vertical position, -1.0 to 1.0, default 0.8)
- `status`: CharField with choices:
  - 'pending' - Job created, not started
  - 'processing_veo' - Generating Veo video
  - 'processing_heygen' - Generating HeyGen avatar
  - 'completed' - Successfully completed
  - 'failed' - Job failed with error
- `progress`: IntegerField (0-100, percentage complete)
- `error_message`: TextField (null=True, stores error details if failed)
- `veo_video_gcs_uri`: CharField (GCS URI of final Veo video, e.g., gs://bucket/path)
- `veo_video_url`: URLField (public HTTPS URL of Veo video)
- `heygen_video_id`: CharField (HeyGen's video ID for tracking)
- `heygen_asset_id`: CharField (HeyGen's asset ID for the uploaded Veo video)
- `final_video_url`: URLField (final merged video URL from HeyGen - THIS IS THE OUTPUT)
- `created_at`: DateTimeField (auto_now_add=True)
- `updated_at`: DateTimeField (auto_now=True)
- `completed_at`: DateTimeField (null=True, when job finished)
- `processing_time_seconds`: IntegerField (null=True, total time taken)
- `credits_used`: IntegerField (for billing/usage tracking, default 0)

**Indexes:**
- (user, created_at) - for user's job history
- (status) - for filtering by status

**Meta:**
- ordering: ['-created_at'] (newest first)

---

## 🔐 AUTHENTICATION & AUTHORIZATION

### **Google Cloud Platform Authentication**

**Service Account Requirements:**
- Create a GCP service account with these roles:
  - `Vertex AI User`
  - `Storage Object Viewer` (to read generated videos)
- Download service account JSON key file
- Store path in environment variable: `GCP_SERVICE_ACCOUNT_FILE`

**Token Management Strategy:**
- Use `google.oauth2.service_account.Credentials`
- Implement singleton pattern for credential manager
- Auto-refresh tokens when expired (before each API call)
- Thread-safe implementation using locks

**Implementation: services/gcp_auth.py**
```python
class GCPAuthManager:
    """
    Singleton class that manages GCP authentication tokens.
    Automatically refreshes expired tokens.
    Thread-safe for concurrent requests.
    """
    - __new__: Implement singleton pattern
    - __init__: Load service account credentials
    - get_access_token(): Return valid token, refresh if needed
```

### **Django API Authentication**

- Use Django REST Framework Token Authentication
- Each user gets a unique token
- Include token in request header: `Authorization: Token <token>`
- Protect all endpoints with `IsAuthenticated` permission

---

## 🎥 VIDEO GENERATION WORKFLOW

### **Complete Pipeline Overview**

```
User Request → Django API → Celery Task → Background Processing:
  1. Generate Veo base video (8s)
  2. Extend Veo video (8s) - Scene 2
  3. Extend Veo video (8s) - Scene 3
  4. Upload Veo video to HeyGen
  5. Generate HeyGen avatar with Veo background
  6. Poll HeyGen until video ready
  7. Save final video URL
  8. Update job status to 'completed'
```

### **Veo Video Generation (services/veo_service.py)**

**VeoService Class Methods:**

1. **generate_base_video(prompt, image_url, storage_uri)**
   - Downloads image from image_url
   - Converts image to base64
   - Calls Veo API: `veo-3.1-generate-preview:predictLongRunning`
   - Parameters:
     - durationSeconds: 8
     - aspectRatio: "9:16" (mobile/vertical format)
     - resolution: "720p"
     - sampleCount: 1
     - resizeMode: "crop"
     - storageUri: GCS path where video will be saved
   - Returns: operation object with operation name

2. **extend_video(video_gcs_uri, prompt, image_url, storage_uri)**
   - Takes existing video GCS URI as input
   - Extends video by additional 8 seconds
   - Uses same Veo API but includes "video" field in request
   - Continues the scene from where previous video ended
   - Returns: operation object with operation name

3. **poll_operation(operation_name, max_retries=30)**
   - Polls Veo operation using `fetchPredictOperation` endpoint
   - Implements exponential backoff: 15s, 30s, 60s, 60s...
   - Maximum wait time per check: 60 seconds
   - Returns: GCS URI of generated video (gs://bucket/path.mp4)
   - Returns None if operation fails or times out

**Key Veo API Endpoints:**
- Generate: `https://us-central1-aiplatform.googleapis.com/v1/projects/{project_id}/locations/us-central1/publishers/google/models/veo-3.1-generate-preview:predictLongRunning`
- Check Status: `https://us-central1-aiplatform.googleapis.com/v1/projects/{project_id}/locations/us-central1/publishers/google/models/veo-3.1-generate-preview:fetchPredictOperation`

**Important Notes:**
- Each Veo generation takes 60-90 seconds
- Videos are stored in GCS automatically by Veo
- Must wait for each operation to complete before starting next extension
- GCS URIs format: `gs://bucket-name/path/to/video.mp4`

### **HeyGen Integration (services/heygen_service.py)**

**HeyGenService Class Methods:**

1. **gcs_to_public_url(gcs_uri)** (static method)
   - Converts: `gs://bucket/path/file.mp4`
   - To: `https://storage.googleapis.com/bucket/path/file.mp4`
   - Required because HeyGen needs public HTTPS URLs

2. **upload_video_asset(video_url)**
   - Uploads Veo video to HeyGen for use as background
   - Endpoint: `POST https://api.heygen.com/v1/asset`
   - Body: `{"url": "https://storage.googleapis.com/..."}`
   - Returns: asset_id (string, used in next step)

3. **generate_avatar_video(avatar_id, voice_id, script, video_asset_id, avatar_scale, avatar_x, avatar_y)**
   - Creates avatar video with Veo video as background
   - Endpoint: `POST https://api.heygen.com/v2/video/generate`
   - Request structure:
     ```json
     {
       "video_inputs": [{
         "character": {
           "type": "avatar",
           "avatar_id": "avatar_id",
           "avatar_style": "normal",
           "scale": 0.8,
           "offset": {"x": 0.7, "y": 0.8},
           "matting": true  // Transparent background
         },
         "voice": {
           "type": "text",
           "input_text": "Script text...",
           "voice_id": "voice_id"
         },
         "background": {
           "type": "video",
           "video_asset_id": "uploaded_asset_id",
           "play_style": "full_video"  // Play entire video
         }
       }],
       "dimension": {"width": 720, "height": 1280},
       "aspect_ratio": "9:16"
     }
     ```
   - Returns: video_id (string, used to check status)

4. **poll_video_status(video_id, max_retries=60)**
   - Checks HeyGen video generation status
   - Endpoint: `GET https://api.heygen.com/v1/video_status.get?video_id={video_id}`
   - Poll every 10 seconds
   - Status values: "pending", "processing", "completed", "failed"
   - Returns: final video URL when status is "completed"
   - Raises exception if status is "failed"

**HeyGen API Headers:**
- `X-Api-Key`: HeyGen API key
- `Content-Type`: application/json

### **Background Task Processing (tasks.py)**

**Celery Task: process_video_job(job_id)**

This is the main background task that orchestrates the entire video generation pipeline.

**Step-by-Step Implementation:**

```python
@shared_task
def process_video_job(job_id):
    """
    Background Celery task to process video generation.
    Runs asynchronously to avoid blocking the API.
    """
    
    async def _process():
        # 1. Load job from database
        job = VideoJob.objects.get(id=job_id)
        
        try:
            # 2. Initialize services
            veo = VeoService()
            heygen = HeyGenService()
            
            # 3. Build full prompts from scenes
            scenes = job.scenes_data
            prompts = [
                f"{job.product_title} | {scene['visual_description']} | "
                f"{scene['camera_movement']} | {scene['mood']}"
                for scene in scenes
            ]
            
            # 4. Prepare GCS storage path
            storage_base = f"gs://{settings.GCS_BUCKET}/{job.product_id or job.id}/{job.created_at.strftime('%Y-%m-%d')}/"
            
            # 5. UPDATE STATUS: Starting Veo generation
            job.status = 'processing_veo'
            job.progress = 10
            job.save()
            
            # 6. Generate base 8-second video
            base_result = await veo.generate_base_video(
                prompts[0],
                job.image_url,
                f"{storage_base}scene_1/"
            )
            scene1_uri = await veo.poll_operation(base_result["name"])
            job.progress = 30
            job.save()
            
            # 7. First extension (16s total)
            ext1_result = await veo.extend_video(
                scene1_uri,
                prompts[1],
                job.image_url,
                f"{storage_base}scene_2/"
            )
            scene2_uri = await veo.poll_operation(ext1_result["name"])
            job.progress = 50
            job.save()
            
            # 8. Second extension (24s total)
            ext2_result = await veo.extend_video(
                scene2_uri,
                prompts[2],
                job.image_url,
                f"{storage_base}scene_3/"
            )
            final_veo_uri = await veo.poll_operation(ext2_result["name"])
            
            # 9. Save Veo video URLs
            job.veo_video_gcs_uri = final_veo_uri
            job.veo_video_url = heygen.gcs_to_public_url(final_veo_uri)
            job.progress = 60
            job.save()
            
            # 10. UPDATE STATUS: Starting HeyGen processing
            job.status = 'processing_heygen'
            job.save()
            
            # 11. Upload Veo video to HeyGen
            asset_id = await heygen.upload_video_asset(job.veo_video_url)
            job.heygen_asset_id = asset_id
            job.progress = 70
            job.save()
            
            # 12. Generate avatar video with Veo background
            video_id = await heygen.generate_avatar_video(
                job.avatar_id,
                job.voice_id,
                job.avatar_script,
                asset_id,
                job.avatar_scale,
                job.avatar_x,
                job.avatar_y
            )
            job.heygen_video_id = video_id
            job.progress = 80
            job.save()
            
            # 13. Poll HeyGen until video is ready
            final_url = await heygen.poll_video_status(video_id)
            
            # 14. UPDATE STATUS: Completed successfully
            job.final_video_url = final_url
            job.status = 'completed'
            job.progress = 100
            job.completed_at = timezone.now()
            job.processing_time_seconds = int((timezone.now() - job.created_at).total_seconds())
            job.credits_used = 1  # Increment for billing
            job.save()
            
        except Exception as e:
            # Handle any errors
            job.status = 'failed'
            job.error_message = str(e)
            job.save()
    
    # Run async function
    asyncio.run(_process())
```

**Key Implementation Details:**
- Use `asyncio.run()` to execute async operations
- Update job status and progress throughout
- Save job to database after each major step
- Comprehensive error handling with try-except
- Store all relevant URLs and IDs for debugging

---

## 🌐 API ENDPOINTS

### **Endpoint 1: Generate Video**

**URL:** `POST /api/video/generate/`

**Authentication:** Required (Token)

**Request Body Schema (serializers.py):**

```python
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
```

**Example Request:**
```json
{
  "product_title": "Premium Wireless Headphones",
  "scenes": [
    {
      "visual_description": "Headphones on modern desk with soft lighting",
      "camera_movement": "slow 360 rotation",
      "mood": "professional and premium",
      "duration": 8
    },
    {
      "visual_description": "Close-up of controls and materials",
      "camera_movement": "smooth zoom in",
      "mood": "sophisticated",
      "duration": 8
    },
    {
      "visual_description": "Headphones being worn showing comfort",
      "camera_movement": "gentle pan",
      "mood": "comfortable",
      "duration": 8
    }
  ],
  "image_url": "https://cdn.example.com/headphones.jpg",
  "avatar_id": "josh_lite3_20230714",
  "voice_id": "d7bbcdd6964c47bdaae26decade4a933",
  "avatar_script": "Introducing our revolutionary wireless headphones...",
  "avatar_position": {
    "scale": 0.8,
    "x": 0.7,
    "y": 0.8
  }
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Video generation started",
  "estimated_time_seconds": 360
}
```

**View Implementation (views.py):**
```python
class VideoGenerationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        # 1. Validate request data
        serializer = VideoGenerationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # 2. Extract avatar position (use defaults if not provided)
        avatar_pos = data.get('avatar_position', {})
        
        # 3. Create VideoJob record
        job = VideoJob.objects.create(
            user=request.user,
            product_id=data.get('product_id'),
            product_title=data['product_title'],
            scenes_data=data['scenes'],
            avatar_script=data['avatar_script'],
            avatar_id=data['avatar_id'],
            voice_id=data['voice_id'],
            image_url=data['image_url'],
            avatar_scale=avatar_pos.get('scale', 0.8),
            avatar_x=avatar_pos.get('x', 0.7),
            avatar_y=avatar_pos.get('y', 0.8),
            status='pending'
        )
        
        # 4. Start background processing
        process_video_job.delay(str(job.id))
        
        # 5. Return immediate response
        return Response({
            'job_id': str(job.id),
            'status': 'pending',
            'message': 'Video generation started',
            'estimated_time_seconds': len(data['scenes']) * 120
        }, status=status.HTTP_202_ACCEPTED)
```

### **Endpoint 2: Get Job Status**

**URL:** `GET /api/video/status/{job_id}/`

**Authentication:** Required (Token)

**Response Schema:**
```python
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
```

**Example Response (Processing):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing_veo",
  "progress": 45,
  "product_title": "Premium Wireless Headphones",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:32:30Z",
  "completed_at": null,
  "processing_time_seconds": null,
  "veo_video_url": null,
  "final_video_url": null,
  "error_message": null,
  "credits_used": 0
}
```

**Example Response (Completed):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 100,
  "product_title": "Premium Wireless Headphones",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:36:00Z",
  "completed_at": "2025-01-15T10:36:00Z",
  "processing_time_seconds": 360,
  "veo_video_url": "https://storage.googleapis.com/bucket/path/veo.mp4",
  "final_video_url": "https://resource.heygen.ai/video/final.mp4",
  "error_message": null,
  "credits_used": 1
}
```

**View Implementation:**
```python
@action(detail=False, methods=['get'], url_path='status/(?P<job_id>[^/.]+)')
def get_status(self, request, job_id=None):
    try:
        # Only allow users to see their own jobs
        job = VideoJob.objects.get(id=job_id, user=request.user)
    except VideoJob.DoesNotExist:
        return Response(
            {'error': 'Job not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = VideoJobSerializer(job)
    return Response(serializer.data)
```

### **Endpoint 3: List User Jobs**

**URL:** `GET /api/video/list_jobs/`

**Authentication:** Required (Token)

**Query Parameters (optional):**
- `status`: Filter by status (pending, processing_veo, processing_heygen, completed, failed)
- `page`: Page number for pagination

**Response:** Array of VideoJob objects (paginated)

**View Implementation:**
```python
@action(detail=False, methods=['get'])
def list_jobs(self, request):
    jobs = VideoJob.objects.filter(user=request.user)
    
    # Optional status filter
    status_filter = request.query_params.get('status')
    if status_filter:
        jobs = jobs.filter(status=status_filter)
    
    serializer = VideoJobSerializer(jobs, many=True)
    return Response(serializer.data)
```

---

## ⚙️ CONFIGURATION & SETTINGS

### **Django Settings (settings.py)**

**Required Additions:**

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',  # For token auth
    'corsheaders',  # For CORS support
    'video_generation',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Must be first
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# Google Cloud Configuration
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
GCP_SERVICE_ACCOUNT_FILE = os.environ.get('GCP_SERVICE_ACCOUNT_FILE')
GCS_BUCKET = os.environ.get('GCS_BUCKET')

# HeyGen Configuration
HEYGEN_API_KEY = os.environ.get('HEYGEN_API_KEY')

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# CORS Settings (adjust for production)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8080",
]
```

### **Celery Configuration (renderly/celery.py)**

**Create new file:**

```python
import os
from celery import Celery

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'renderly.settings')

# Create Celery app
app = Celery('renderly')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

**Update renderly/__init__.py:**

```python
from .celery import app as celery_app

__all__ = ('celery_app',)
```

### **Environment Variables (.env)**

**Create .env file in project root:**

```env
# Django
SECRET_KEY=your-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (PostgreSQL for production)
DATABASE_URL=postgresql://user:password@localhost:5432/video_saas

# Google Cloud Platform
GCP_PROJECT_ID=your-gcp-project-id
GCP_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
GCS_BUCKET=your-gcs-bucket-name

# HeyGen
HEYGEN_API_KEY=your-heygen-api-key

# Redis (for Celery)
REDIS_URL=redis://localhost:6379/0
```

### **Requirements.txt**

```
Django>=4.2,<5.0
djangorestframework>=3.14.0
django-cors-headers>=4.0.0
celery>=5.3.0
redis>=4.5.0
google-cloud-aiplatform>=1.38.0
google-auth>=2.23.0
httpx>=0.25.0
python-dotenv>=1.0.0
psycopg2-binary>=2.9.9  # PostgreSQL
Pillow>=10.0.0
```

---

## 🔍 ERROR HANDLING & VALIDATION

### **Request Validation**

- Use DRF serializers for all input validation
- Validate scene count (1-20 scenes)
- Validate avatar position values (-1.0 to 1.0 for x/y, 0.1 to 1.0 for scale)
- Validate URLs are properly formatted
- Validate required fields are present

### **API Error Responses**

**400 Bad Request:**
```json
{
  "error": "Validation error",
  "details": {
    "scenes": ["Ensure this field has at least 1 element."],
    "image_url": ["Enter a valid URL."]
  }
}
```

**401 Unauthorized:**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**404 Not Found:**
```json
{
  "error": "Job not found"
}
```

**500 Internal Server Error:**
```json
{
  "error": "Internal server error",
  "message": "An unexpected error occurred"
}
```

### **Background Task Error Handling**

In tasks.py, wrap all operations in try-except:

```python
try:
    # Process video generation
    ...
except Exception as e:
    job.status = 'failed'
    job.error_message = str(e)
    job.save()
    
    # Optional: Log to external service (Sentry, etc.)
    logger.error(f"Video generation failed for job {job.id}: {str(e)}")
```

---

## 🧪
### Tests Overview

- Use Django’s test runner with `video_generation/tests.py`
- Cover serializers, views, Celery task orchestration, and service integrations
- Mock external HTTP calls (Veo, HeyGen) to keep tests deterministic
- Run with `python manage.py test`

#### Serializer Tests

```python
from django.test import TestCase
from video_generation.serializers import (
    VideoGenerationRequestSerializer,
    SceneSerializer,
    AvatarPositionSerializer,
)

class SerializerValidationTests(TestCase):
    def test_valid_request(self):
        payload = {
            "product_title": "Premium Wireless Headphones",
            "scenes": [
                {"visual_description": "A", "camera_movement": "B", "mood": "C", "duration": 8},
                {"visual_description": "D", "camera_movement": "E", "mood": "F", "duration": 8},
                {"visual_description": "G", "camera_movement": "H", "mood": "I", "duration": 8},
            ],
            "image_url": "https://example.com/img.jpg",
            "avatar_id": "avatar_123",
            "voice_id": "voice_123",
            "avatar_script": "Script text...",
            "avatar_position": {"scale": 0.8, "x": 0.7, "y": 0.8},
        }
        s = VideoGenerationRequestSerializer(data=payload)
        self.assertTrue(s.is_valid(), s.errors)

    def test_avatar_position_bounds(self):
        payload = {
            "product_title": "T",
            "scenes": [{"visual_description": "A", "camera_movement": "B", "mood": "C", "duration": 8}],
            "image_url": "https://example.com/img.jpg",
            "avatar_id": "avatar_123",
            "voice_id": "voice_123",
            "avatar_script": "Script",
            "avatar_position": {"scale": 1.2, "x": -1.5, "y": 2.0},
        }
        s = VideoGenerationRequestSerializer(data=payload)
        self.assertFalse(s.is_valid())
```

#### View Tests

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

class ViewEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u", "u@example.com", "p")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_generate_starts_job(self):
        payload = {
            "product_title": "Premium Wireless Headphones",
            "scenes": [
                {"visual_description": "A", "camera_movement": "B", "mood": "C", "duration": 8},
                {"visual_description": "D", "camera_movement": "E", "mood": "F", "duration": 8},
                {"visual_description": "G", "camera_movement": "H", "mood": "I", "duration": 8},
            ],
            "image_url": "https://example.com/img.jpg",
            "avatar_id": "avatar_123",
            "voice_id": "voice_123",
            "avatar_script": "Script text...",
        }
        res = self.client.post("/api/video/generate/", payload, format="json")
        self.assertEqual(res.status_code, 202)
        self.assertIn("job_id", res.data)
```

#### Task Orchestration Tests

```python
from django.test import TestCase
from unittest.mock import patch
from video_generation.models import VideoJob
from video_generation.tasks import process_video_job
from django.utils import timezone

class TaskPipelineTests(TestCase):
    @patch("video_generation.services.veo_service.VeoService.generate_base_video")
    @patch("video_generation.services.veo_service.VeoService.extend_video")
    @patch("video_generation.services.veo_service.VeoService.poll_operation")
    @patch("video_generation.services.heygen_service.HeyGenService.upload_video_asset")
    @patch("video_generation.services.heygen_service.HeyGenService.generate_avatar_video")
    @patch("video_generation.services.heygen_service.HeyGenService.poll_video_status")
    def test_process_job_success(self, poll_final, gen_avatar, upload_asset, poll_op, extend, gen_base):
        gen_base.return_value = {"name": "op1"}
        extend.side_effect = [{"name": "op2"}, {"name": "op3"}]
        poll_op.side_effect = [
            "gs://bucket/scene1.mp4",
            "gs://bucket/scene2.mp4",
            "gs://bucket/final.mp4",
        ]
        upload_asset.return_value = "asset_1"
        gen_avatar.return_value = "video_1"
        poll_final.return_value = "https://heygen.example/final.mp4"

        job = VideoJob.objects.create(
            user=None,  # set to a real user in fixtures
            product_title="T",
            scenes_data=[{"visual_description": "A", "camera_movement": "B", "mood": "C", "duration": 8}] * 3,
            avatar_script="Script",
            avatar_id="avatar_123",
            voice_id="voice_123",
            image_url="https://example.com/img.jpg",
            status="pending",
        )

        process_video_job.delay(str(job.id))
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.progress, 100)
        self.assertIsNotNone(job.final_video_url)
```

---

## 🔧 URL Routing

### Project URLs (`renderly/urls.py`)

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('video_generation.urls')),
]
```

### App URLs (`video_generation/urls.py`)

```python
from rest_framework.routers import DefaultRouter
from .views import VideoGenerationViewSet

router = DefaultRouter()
router.register('video', VideoGenerationViewSet, basename='video')

urlpatterns = router.urls
```

---

## 🗄️ Database & Env Loading

### `.env` loading in `settings.py`

```python
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
TIME_ZONE = 'UTC'
USE_TZ = True
```

### Database configuration

```python
import dj_database_url

DATABASES = {
    'default': dj_database_url.parse(
        os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR / "db.sqlite3"}'),
        conn_max_age=600,
        ssl_require=False,
    )
}
```

Add `dj-database-url` to requirements.

---

## ⚡ Async Strategy

- Option A (recommended for simplicity): Use synchronous Celery task and `httpx.Client` in services
- Option B: Keep async services with `httpx.AsyncClient`, wrap ORM calls using `asgiref.sync.sync_to_async`, and call with `asyncio.run()`

### Option A outline

```python
from celery import shared_task
from video_generation.models import VideoJob
from video_generation.services.veo_service import VeoService
from video_generation.services.heygen_service import HeyGenService
from django.utils import timezone

@shared_task
def process_video_job(job_id):
    job = VideoJob.objects.get(id=job_id)
    veo = VeoService()      # uses httpx.Client
    heygen = HeyGenService()  # uses httpx.Client
    # same pipeline: update status/progress and handle errors
```

---

## 🔔 Webhook Delivery

- If `webhook_url` is provided, POST job summary upon completion or failure
- Include retry with exponential backoff

```python
import time, httpx

def deliver_webhook(webhook_url, payload, attempts=5):
    for i in range(attempts):
        try:
            httpx.post(webhook_url, json=payload, timeout=10)
            return True
        except Exception:
            time.sleep(min(60, 2 ** i))
    return False
```

Call after updating `job.status` and `final_video_url`.

---

## 🧾 Logging

### Logging config in `settings.py`

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'video_generation': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
```

Use `logger = logging.getLogger(__name__)` in services and tasks.

---

## ▶️ Run & Dev

- Create venv: `python -m venv .venv` and activate `.\.venv\Scripts\activate`
- Install deps: `pip install -r requirements.txt`
- Migrate: `python manage.py migrate`
- Create admin: `python manage.py createsuperuser`
- Run API: `python manage.py runserver`
- Start Redis (Docker): `docker run -p 6379:6379 redis:7`
- Start Celery worker: `celery -A renderly worker -l info`
- Optional Celery beat: `celery -A renderly beat -l info`

### Token Auth

- Ensure `rest_framework.authtoken` is installed and migrated
- Create token: `python manage.py drf_create_token <username>`
- Use header: `Authorization: Token <token>`

---

## 📦 Requirements Updates

Add:

```
dj-database-url>=2.1.0
```

Optional for tests:

```
responses>=0.25.0
```

---

## 🔐 Security Notes

- Keep `.env` out of version control and rotate keys periodically
- Restrict `CORS_ALLOWED_ORIGINS` to trusted domains in production
- Limit service account roles to minimum required
- Consider signed URLs for GCS if buckets are private
