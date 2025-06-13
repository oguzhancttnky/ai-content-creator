# AI Content Creator Pipeline

An automated AI-powered pipeline that generates short story videos for social media platforms using AWS Lambda, S3, and RunPod.
Social media platforms prevent automated publishing contents so I couldn't manage to make the system fully automatically works. So you will need to manually upload the generated videos.

## Overview

```
Scheduled Trigger → AWS Lambda → Deepseek API → ElevenLabs API → S3 Upload → Start RunPod Instance → FLUX.1-dev → Video Generation → S3 Upload → Stop RunPod Instance → Social Media Publishing (Optional)
```

The pipeline consists of two main components:

1. **Content Generator** (AWS Lambda): Generates scripts, voiceovers, and starts video processing
2. **Video Generator** (RunPod): Creates synchronized videos using FLUX.1-dev AI model

## Features

- **AI-Generated Content**: Uses Deepseek API for short story scripts and image prompts
- **Realistic Voiceovers**: ElevenLabs text-to-speech with word-level timestamps
- **High-Quality Visuals**: FLUX.1-dev model for photorealistic image generation
- **Perfect Synchronization**: Caption timing with voiceover
- **Cost-Effective**: Pay-per-use Lambda + on-demand RunPod instances

## Project Structure

```
ai-content-creator/
├── content-script-generator-and-pod-runner.py  # Lambda: Content generation
├── runpod-video-generator.py                   # RunPod: Video creation
├── start.sh                                    # RunPod initialization script
└── README.md
```

## Setup Requirements

### AWS Services
- **Lambda Functions**: Content generation
- **S3 Bucket**: File storage
- **IAM Roles**: Proper permissions for Lambda and S3

### RunPod Configuration
- **GPU Instance**: NVIDIA A40
- **Container Disk**: 50GB for model caching
- **Volume Disk**: 5GB for temporary files

### API Keys Required
- **Deepseek API**: Content and prompt generation
- **ElevenLabs API**: Voiceover synthesis
- **RunPod API**: Instance management
- **Hugging Face Token**: Model access

## Deployment

### Step 1: AWS Lambda Setup

#### Lambda Function 1: Content Generator
```bash
# Create deployment package
zip -r content-creator.zip content-script-generator-and-pod-runner.py

# Deploy to AWS Lambda
aws lambda create-function \
  --function-name ai-content-creator \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT:role/lambda-execution-role \
  --handler content-script-generator-and-pod-runner.lambda_handler \
  --zip-file fileb://content-creator.zip \
  --timeout 900 \
  --memory-size 512
```

### Step 2: Environment Variables

#### Content Generator Lambda
```bash
DEEPSEEK_API_KEY=your_deepseek_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
S3_BUCKET=your-bucket
RUNPOD_API_KEY=your_runpod_api_key
RUNPOD_POD_ID=your_runpod_pod_id
```

#### RunPod Instance
```bash
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=us-east-1
HUGGINGFACE_TOKEN=your_hf_token
STOPPING_RUNPOD_POD_ID=your_runpod_pod_id
STOPPING_RUNPOD_API_KEY=your_runpod_api_key
```

### Step 3: RunPod Instance Setup

1. **Create RunPod Instance**:
   ```bash
   # Use PyTorch 2.0+ template with CUDA support (runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04)
   # Minimum 24GB VRAM for FLUX.1-dev (48GB for best results)
   ```

2. **Upload Files**:
   ```bash
   # Upload to /workspace/ directory
   - runpod-video-generator.py
   - start.sh
   ```
3. **Set Flask Port**:
   Add HTTP port 8000 to pod instance

4. **Set Startup Script**:
   ```bash
   bash /workspace/start.sh
   ```

### Step 4: S3 Bucket Configuration

#### Bucket Structure
```
your-bucket/
├── transcripts/         # Generated scripts with timestamps
├── audio/               # MP3 voiceovers
├── images/              # Generated clip images
├── videos/              # Final MP4 videos
├── metadata/            # Video metadata for publishing
└── errors/              # Error logs
```

### Step 5: Automation Schedule

#### EventBridge Rule (Daily Trigger)
```json
{
  "Name": "DailyVideoGeneration",
  "ScheduleExpression": "cron(0 12 * * ? *)",
  "State": "ENABLED",
  "Targets": [
    {
      "Id": "ContentCreatorTarget",
      "Arn": "arn:aws:lambda:region:account:function:ai-content-creator"
    }
  ]
}
```

## Pipeline Flow

### 1. Content Generation (Lambda)
- Fetches random story inspiration from API
- Generates video script using Deepseek AI
- Creates word-level timestamps with ElevenLabs
- Generates image prompts for each video clip
- Uploads assets to S3
- Starts RunPod instance

### 2. Video Creation (RunPod)
- Downloads transcript and audio from S3
- Loads FLUX.1-dev model for image generation
- Creates synchronized video clips with captions
- Merges clips with perfectly timed voiceover
- Uploads final video to S3
- Auto-stops instance to save costs

### 3. Publishing (Lambda) (Optional)
- Triggered by S3 video upload event
- Downloads video and metadata
- Publishes to configured social platforms

## Configuration Options

### Video Specifications
```python
# Adjustable in content-script-generator-and-pod-runner.py
story_duration = random.randrange(32, 61, 4)  # 32-60 seconds
video_resolution = (1080, 1080)  # Square format
fps = 30
bitrate = '2000k'
```

### AI Model Settings
```python
# Deepseek API parameters
temperature = 0.85
top_p = 0.95
frequency_penalty = 0.4

# FLUX.1-dev parameters
num_inference_steps = 20
guidance_scale = 3.5
```

## Cost Estimation Monthly (1 video/day)

| Service | Usage | Cost |
|---------|-------|------|
| AWS Lambda | 30 executions | ~$0.01 |
| AWS S3 | 300-600MB | ~$0,01 |
| RunPod GPU | ~8-10h (On Demand A40 $0.4/hr) | ~$4 | 
| Deepseek API | 600.000 token | ~$0,1 |
| ElevenLabs | 30.000 token | $5 |
| **Total** | | **~$9/month** |

---