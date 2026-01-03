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
video_saas/
├── manage.py
├── requirements.txt
├── .env
├── .gitignore
├── README.md
├── video_saas/                    # Main project directory
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

### **Celery Configuration (video_saas/celery.py)**

**Create new file:**

```python
import os
from celery import Celery

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'video_saas.settings')

# Create Celery app
app = Celery('video_saas')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

**Update video_saas/__init__.py:**

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

## 🧪 TESTING REQUIREMENTS

### **Unit Tests (video_generation/tests.py)**

**Required Test Cases:**

1. **Model Tests:**
   - Test VideoJob creation with all fields
   - Test status choices validation
   - Test UUID generation
   - Test timestamps (created_at, updated_at)

2. **Serializer Tests:**
   - Test valid scene data serialization
   - Test invalid scene data (missing fields, wrong types)
   - Test avatar position validation (out of range values)
   - Test minimum/maximum scene count

3. **Service Tests (Mock External APIs):**
   - Test GCP token refresh logic
   - Test Veo video generation (mock API response)
   - Test HeyGen upload and generation (mock API response)
   - Test GCS URI to public URL conversion

4. **API Endpoint Tests:**
   - Test POST /api/video/generate/ with valid data
   - Test POST /api/video/generate/ with invalid data
   - Test GET /api/video/status/{job_id}/ for own job
   - Test GET /api/video/status/{job_id}/ for another user's job (should fail)
   - Test authentication required for all endpoints

### **Integration Tests**

**Manual Testing Checklist:**

1. Create user and generate auth token
2. Submit video generation request
3. Verify job created in database
4. Monitor Celery logs for task execution
5. Check job status progression (pending → processing_veo → processing_heygen → completed)
6. Verify final_video_url is accessible
7. Test error scenarios (invalid avatar_id, network failures)

---

## 📦 DEPLOYMENT INSTRUCTIONS

### **Local Development Setup**

```bash
# 1. Clone and setup
git clone <repository>
cd video_saas
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Create .env file with your credentials

# 3. Run migrations
python manage.py makemigrations
python manage.py migrate

# 4. Create superuser
python manage.py createsuperuser

# 5. Create auth token for user
python manage.py shell
>>> from django.contrib.auth.models import User
>>> from rest_framework.authtoken.models import Token
>>> user = User.objects.get(username='your_username')
>>> token = Token.objects.create(user=user)
>>> print(token.key)

# 6. Start Redis (in separate terminal)
redis-server

# 7. Start Celery worker (in separate terminal)
celery -A video_saas worker --loglevel=info

# 8. Start Django server
python manage.py runserver
```

### **Docker Deployment**

**Create Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Run gunicorn
CMD ["gunicorn", "video_saas.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
```

**Create docker-compose.yml:**

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - db
      - redis
    volumes:
      - ./:/app
  
  celery:
    build: .
    command: celery -A video_saas worker --loglevel=info
    env_file:
      - .env
    depends_on:
      - redis
      - db
  
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: video_saas
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

### **Production Deployment (Google Cloud Run)**

```bash
# 1. Build and push to Container Registry
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/video-api

# 2. Deploy to Cloud Run
gcloud run deploy video-api \
  --image gcr.io/YOUR_PROJECT_ID/video-api \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT_ID=your-project,HEYGEN_API_KEY=your-key,REDIS_URL=redis://redis-host:6379"

# 3. Deploy Celery worker as separate service
gcloud run deploy video-celery-worker \
  --image gcr.io/YOUR_PROJECT_ID/video-api \
  --platform managed \
  --region us-central1 \
  --command "celery,-A,video_saas,worker,--loglevel=info" \
  --no-allow-unauthenticated
```

---

## 🎨 DJANGO ADMIN CONFIGURATION

### **Admin Interface (admin.py)**

**Configure VideoJob admin:**

```python
from django.contrib import admin
from .models import VideoJob

@admin.register(VideoJob)
class VideoJobAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'product_title', 'status', 
        'progress', 'created_at', 'completed_at', 'credits_used'
    ]
    list_filter = ['status', 'created_at', 'user']
    search_fields = ['product_title', 'product_id', 'id']
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'completed_at',
        'processing_time_seconds', 'veo_video_gcs_uri',
        'veo_video_url', 'heygen_video_id', 'heygen_asset_id',
        'final_video_url'
    ]
    
    fieldsets = (
        ('Job Information', {
            'fields': ('id', 'user', 'product_id', 'product_title', 'status', 'progress')
        }),
        ('Video Configuration', {
            'fields': ('scenes_data', 'image_url', 'avatar_id', 'voice_id', 'avatar_script')
        }),
        ('Avatar Position', {
            'fields': ('avatar_scale', 'avatar_x', 'avatar_y')
        }),
        ('Results', {
            'fields': ('veo_video_gcs_uri', 'veo_video_url', 'heygen_video_id', 
                      'heygen_asset_id', 'final_video_url')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'completed_at', 
                      'processing_time_seconds', 'credits_used', 'error_message')
        }),
    )
    
    def has_add_permission(self, request):
        return False  # Jobs should only be created via API
```

---

## 🔒 SECURITY CONSIDERATIONS

### **API Security**

1. **Rate Limiting:**
   - Install: `pip install django-ratelimit`
   - Add rate limits to generate endpoint (e.g., 10 requests per hour per user)

2. **Input Sanitization:**
   - Validate all user inputs through serializers
   - Sanitize image URLs to prevent SSRF attacks
   - Limit script length to prevent abuse

3. **Authentication:**
   - Use HTTPS in production (enforce with SECURE_SSL_REDIRECT)
   - Rotate tokens periodically
   - Implement token expiration

4. **Environment Variables:**
   - Never commit .env file to git
   - Use secrets management in production (AWS Secrets Manager, GCP Secret Manager)
   - Rotate API keys regularly

### **Data Privacy**

1. **User Data:**
   - Only show users their own jobs (enforced in views)
   - Store minimal personal information
   - Implement data deletion on user request

2. **Video Storage:**
   - Set appropriate GCS bucket permissions
   - Use signed URLs for temporary access
   - Implement video retention policies

---

## 📊 MONITORING & LOGGING

### **Logging Configuration (settings.py)**

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'video_generation.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'video_generation': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### **Monitoring Metrics**

**Track these metrics:**
- Video generation success rate
- Average processing time per video
- Failed job count and reasons
- API response times
- Celery queue length
- Credits consumed per user

**Implement health check endpoint:**

```python
@action(detail=False, methods=['get'])
def health(self, request):
    """Health check endpoint for monitoring"""
    return Response({
        'status': 'healthy',
        'timestamp': timezone.now(),
        'database': 'connected',  # Add actual DB check
        'redis': 'connected',  # Add actual Redis check
    })
```

---

## 💰 SAAS FEATURES (FUTURE ENHANCEMENTS)

### **Billing Integration**

**Add to VideoJob model:**
```python
cost_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
```

**Pricing structure:**
- Calculate cost based on video length: $0.10 per 8 seconds
- Track in `credits_used` field
- Integrate with Stripe for payments

### **User Plans**

**Create UserProfile model:**
```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    plan = models.CharField(choices=[
        ('free', 'Free - 5 videos/month'),
        ('pro', 'Pro - 50 videos/month'),
        ('enterprise', 'Enterprise - Unlimited')
    ])
    videos_this_month = models.IntegerField(default=0)
    total_credits = models.IntegerField(default=5)
```

### **Webhooks**

**Implement webhook notifications:**
```python
def send_webhook_notification(job):
    if job.webhook_url:
        requests.post(job.webhook_url, json={
            'job_id': str(job.id),
            'status': job.status,
            'final_video_url': job.final_video_url
        })
```

---

## 📝 ADDITIONAL IMPLEMENTATION NOTES

### **Dynamic Scene Count**

The system is designed to be flexible:
- 1 scene = 8 seconds (no extensions)
- 2 scenes = 16 seconds (1 extension)
- 3 scenes = 24 seconds (2 extensions)
- N scenes = N × 8 seconds

**Implementation in tasks.py:**

```python
# Generate base video from first scene
video_uri = await veo.generate_base_video(prompts[0], ...)

# Loop through remaining scenes for extensions
for i, prompt in enumerate(prompts[1:], start=1):
    video_uri = await veo.extend_video(video_uri, prompt, ...)
    job.progress = 30 + (i * 30 / len(prompts))
    job.save()
```

### **Avatar Positioning Presets**

Provide helper constants for common layouts:

```python
AVATAR_PRESETS = {
    'bottom_right': {'scale': 0.8, 'x': 0.7, 'y': 0.8},
    'bottom_left': {'scale': 0.8, 'x': -0.7, 'y': 0.8},
    'top_right': {'scale': 0.8, 'x': 0.7, 'y': -0.8},
    'top_left': {'scale': 0.8, 'x': -0.7, 'y': -0.8},
    'center': {'scale': 1.0, 'x': 0.0, 'y': 0.0},
}
```

### **Retry Logic**

Add retry logic for transient failures:

```python
from celery import Task

class RetryableTask(Task):
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 60}
    retry_backoff = True
```

---

## 🎯 SUCCESS CRITERIA

**The implementation is complete when:**

1. ✅ User can submit video generation request via API
2. ✅ System creates VideoJob in database with status 'pending'
3. ✅ Celery task starts automatically
4. ✅ Veo generates base video and extensions sequentially
5. ✅ Videos are uploaded to HeyGen successfully
6. ✅ HeyGen generates avatar with Veo video background
7. ✅ Final video URL is returned in completed job
8. ✅ User can check job status at any time
9. ✅ All errors are caught and stored in error_message
10. ✅ Job progress updates throughout the pipeline
11. ✅ Authentication is required and enforced
12. ✅ Users can only access their own jobs
13. ✅ Admin interface shows all jobs with filters
14. ✅ System handles multiple concurrent requests
15. ✅ All environment variables are configurable

---

## 🚀 GETTING STARTED CHECKLIST FOR CURSOR AI

**Phase 1: Project Setup**
- [ ] Create Django project structure
- [ ] Install all dependencies from requirements.txt
- [ ] Configure settings.py with all required settings
- [ ] Set up .env file with credentials
- [ ] Initialize database and run migrations

**Phase 2: Core Models**
- [ ] Create VideoJob model with all fields
- [ ] Add indexes and meta options
- [ ] Create and run migrations
- [ ] Configure admin.py for VideoJob

**Phase 3: Services**
- [ ] Implement GCPAuthManager with token refresh
- [ ] Implement VeoService with generate, extend, and poll methods
- [ ] Implement HeyGenService with upload and generate methods
- [ ] Test services individually with mock data

**Phase 4: API Layer**
- [ ] Create all serializers with validation
- [ ] Implement VideoGenerationViewSet with generate endpoint
- [ ] Implement status and list_jobs endpoints
- [ ] Configure URL routing

**Phase 5: Background Processing**
- [ ] Set up Celery configuration
- [ ] Implement process_video_job task
- [ ] Add progress tracking throughout pipeline
- [ ] Implement comprehensive error handling

**Phase 6: Testing**
- [ ] Write unit tests for models and serializers
- [ ] Write integration tests for API endpoints
- [ ] Manual testing with real credentials
- [ ] Load testing with multiple concurrent requests

**Phase 7: Deployment**
- [ ] Create Dockerfile and docker-compose.yml
- [ ] Test Docker deployment locally
- [ ] Deploy to production environment
- [ ] Set up monitoring and logging

---

## 📖 FINAL NOTES FOR AI CODE EDITOR

**This is a production-ready, enterprise-grade Django application that:**

1. Handles complex, long-running video generation workflows asynchronously
2. Integrates with two external AI APIs (Google Vertex AI and HeyGen)
3. Manages authentication, authorization, and multi-user access
4. Provides comprehensive error handling and status tracking
5. Is architected for scalability and SaaS deployment
6. Includes proper security measures and data privacy
7. Has full admin interface and monitoring capabilities
8. Supports dynamic video lengths based on scene count
9. Returns a single, merged, production-ready video URL as output

**Key Technical Decisions:**
- Django + DRF for robust API framework
- Celery + Redis for reliable background processing
- PostgreSQL for production database
- Service classes for clean separation of concerns
- Comprehensive serializers for validation
- Token authentication for API security

**The workflow is:**
Request → API → Database → Celery → Veo (3 steps) → HeyGen (2 steps) → Final Video URL

**Expected total processing time:** 5-7 minutes per video

Build this exactly as specified for a robust, scalable video generation API!