I'll do a thorough research on HeyGen's API to find the exact endpoint and requirements for your use case.Let me fetch the official HeyGen API documentation to get the exact endpoint details:Now let me search for specific information about adding custom video backgrounds or B-roll to HeyGen videos:Now let me search for the Upload Asset API which is crucial for uploading your Veo video:Let me fetch the detailed Upload Asset API documentation:Now let me fetch the Create Avatar Video V2 endpoint to see the exact payload structure:Now let me search for more information about the video status endpoint:Perfect! Now I have comprehensive information. Let me create a detailed analysis document for you:

Based on my thorough research of HeyGen's API documentation, here's the **complete workflow** to merge your Veo-generated B-roll video with a HeyGen avatar and script:

## **Complete Workflow Summary**

### **Step 1: Upload Your Veo B-roll Video to HeyGen**
**Endpoint:** `POST https://upload.heygen.com/v1/asset`

**Headers:**
```
X-Api-Key: <your-heygen-api-key>
Content-Type: multipart/form-data
```

**Request Body:**
- Upload your Veo video file as `multipart/form-data`
- The API accepts video files (mp4, mov, etc.)

**Response:**
```json
{
  "code": 100,
  "data": {
    "video_asset_id": "<asset_id>",
    "url": "<asset_url>"
  },
  "message": "Success"
}
```

**Save the `video_asset_id`** - you'll need this for Step 2.

---

### **Step 2: Create Avatar Video with Your B-roll as Background**
**Endpoint:** `POST https://api.heygen.com/v2/video/generate`

**Headers:**
```
X-Api-Key: <your-heygen-api-key>
Content-Type: application/json
```

**Request Payload:**
```json
{
  "video_inputs": [
    {
      "character": {
        "type": "avatar",
        "avatar_id": "<your_chosen_avatar_id>",
        "avatar_style": "normal"
      },
      "voice": {
        "type": "text",
        "input_text": "<your_script_describing_the_product>",
        "voice_id": "<your_chosen_voice_id>",
        "speed": 1.0
      },
      "background": {
        "type": "video",
        "video_asset_id": "<asset_id_from_step_1>",
        "play_style": "loop"
      }
    }
  ],
  "dimension": {
    "width": 1280,
    "height": 720
  },
  "title": "Product Demo with Veo B-roll"
}
```

**Background Options:**
- `play_style`: Can be `"fit_to_scene"`, `"freeze"`, `"loop"`, or `"full_video"`
- **Alternative:** You can use `"url"` instead of `"video_asset_id"` if you have a publicly accessible URL for your Veo video (but using uploaded assets is more reliable)

**Response:**
```json
{
  "code": 100,
  "data": {
    "video_id": "<video_id>"
  },
  "message": "Success"
}
```

**Save the `video_id`** - you'll need this for Step 3.

---

### **Step 3: Check Video Generation Status**
**Endpoint:** `GET https://api.heygen.com/v1/video_status.get?video_id=<video_id>`

**Headers:**
```
X-Api-Key: <your-heygen-api-key>
Accept: application/json
```

**Poll this endpoint every 5-10 seconds** until status is `"completed"`.

**Status Values:**
- `"pending"` - Queued, waiting to start
- `"processing"` - Currently rendering
- `"completed"` - Video is ready (contains `video_url`)
- `"failed"` - Generation failed (contains error details)

**Response (when completed):**
```json
{
  "code": 100,
  "data": {
    "id": "<video_id>",
    "status": "completed",
    "video_url": "<downloadable_video_url>",
    "thumbnail_url": "<thumbnail_url>",
    "duration": 45.2,
    "gif_url": "<gif_preview_url>",
    "caption_url": "<caption_url>",
    "error": null
  },
  "message": "Success"
}
```

---

### **Step 4: Get Final Video URL**
Once status is `"completed"`, extract the `video_url` from the response.

**Important Notes:**
- The `video_url` expires in **7 days**
- Each time you call the status endpoint, the URL and its expiration parameters are regenerated
- Download and save the video within the 7-day window

---

## **Required Preparations**

### **Get Available Avatars:**
```bash
GET https://api.heygen.com/v2/avatars
Headers: X-Api-Key: <your-api-key>
```

### **Get Available Voices:**
```bash
GET https://api.heygen.com/v2/voices
Headers: X-Api-Key: <your-api-key>
```

---

## **Complete Python Example**

```python
import requests
import time
import json

API_KEY = "your-heygen-api-key"
VEO_VIDEO_PATH = "path/to/your/veo_broll.mp4"
SCRIPT = "Check out this amazing product! It features cutting-edge design and innovative functionality..."

# Step 1: Upload Veo B-roll
def upload_veo_video():
    url = "https://upload.heygen.com/v1/asset"
    headers = {"X-Api-Key": API_KEY}
    
    with open(VEO_VIDEO_PATH, 'rb') as video_file:
        files = {'file': video_file}
        response = requests.post(url, headers=headers, files=files)
    
    data = response.json()
    return data['data']['video_asset_id']

# Step 2: Create avatar video with B-roll background
def create_avatar_video(video_asset_id, avatar_id, voice_id):
    url = "https://api.heygen.com/v2/video/generate"
    headers = {
        "X-Api-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "video_inputs": [{
            "character": {
                "type": "avatar",
                "avatar_id": avatar_id,
                "avatar_style": "normal"
            },
            "voice": {
                "type": "text",
                "input_text": SCRIPT,
                "voice_id": voice_id,
                "speed": 1.0
            },
            "background": {
                "type": "video",
                "video_asset_id": video_asset_id,
                "play_style": "loop"
            }
        }],
        "dimension": {
            "width": 1280,
            "height": 720
        }
    }
    
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    return data['data']['video_id']

# Step 3: Poll for completion
def wait_for_video(video_id):
    url = f"https://api.heygen.com/v1/video_status.get?video_id={video_id}"
    headers = {
        "X-Api-Key": API_KEY,
        "Accept": "application/json"
    }
    
    while True:
        response = requests.get(url, headers=headers)
        data = response.json()['data']
        status = data['status']
        
        print(f"Status: {status}")
        
        if status == "completed":
            return data['video_url']
        elif status == "failed":
            raise Exception(f"Video generation failed: {data.get('error')}")
        
        time.sleep(5)

# Main workflow
print("Step 1: Uploading Veo B-roll...")
video_asset_id = upload_veo_video()
print(f"Uploaded! Asset ID: {video_asset_id}")

print("\nStep 2: Creating avatar video...")
avatar_id = "your-avatar-id"  # Get from List Avatars API
voice_id = "your-voice-id"    # Get from List Voices API
video_id = create_avatar_video(video_asset_id, avatar_id, voice_id)
print(f"Video generation started! Video ID: {video_id}")

print("\nStep 3: Waiting for completion...")
final_url = wait_for_video(video_id)
print(f"\n✅ Video ready! URL: {final_url}")
```

---

## **Critical Points**

1. **Asset Upload is Required:** You MUST upload your Veo video to HeyGen first to get the `video_asset_id`. Direct URLs from external sources often fail validation.

2. **Background Placement:** The `background` property goes **inside each video_input object**, not at the root level.

3. **Video Expiration:** Download URLs expire in 7 days. Store or re-fetch as needed.

4. **Rate Limits:** Be mindful of API rate limits. Implement proper retry logic.

5. **Alternative to video_asset_id:** You can use `"url"` instead, but uploaded assets are more reliable:
```json
"background": {
  "type": "video",
  "url": "https://your-public-url.com/video.mp4",
  "play_style": "loop"
}
```

This is the complete, verified workflow based on HeyGen's official API documentation. No guessing - all endpoints and parameters are confirmed from their docs.