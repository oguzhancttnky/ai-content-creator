import json
import os
import boto3
import torch
import threading
from diffusers import FluxPipeline
from moviepy import AudioFileClip, CompositeVideoClip, TextClip, vfx, ImageClip, ColorClip
from flask import Flask, request, jsonify
import requests
import traceback

def create_captions(clip_data):
    text_clips = []
    word_timestamps = clip_data['word_timestamps']
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    for word_data in word_timestamps:
        start = word_data["start"]
        end = word_data["end"]
        word_text = word_data["word"]
        txt_clip = (
            TextClip(text=word_text, font=font_path, font_size=60, color='white', stroke_color='black',
                     stroke_width=3, method="caption", size = (1080, 240))
            .with_position(("center", "bottom"))
            .with_start(start)
            .with_end(end)
            .with_duration(end - start)
            .with_effects([vfx.CrossFadeIn(0.1)])
        )
        text_clips.append(txt_clip)

    return text_clips

def generate_video_from_images(transcript_data, audio_path, output_path, s3_bucket, video_id):
    print("=== Starting image-based video generation with FLUX.1-dev ===")
    print(f"Script: {transcript_data['script']}")
    print(f"Duration: {transcript_data.get('duration', 'unknown')} seconds")
    print(f"Clip count: {transcript_data.get('clip_count', 'unknown')}")

    # Load FLUX.1-dev model from Hugging Face
    model_id = "black-forest-labs/FLUX.1-dev"
    print(f"Loading model: {model_id}")

    try:
        # Load FLUX pipeline
        pipe = FluxPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16
        )
        pipe.to("cuda")
        print("FLUX.1-dev model loaded successfully")
    except Exception as e:
        print(f"✗ Error loading model: {str(e)}")
        raise e

    # Get audio and clip data
    print("=== Processing audio and clips ===")
    audio_clip = AudioFileClip(audio_path)
    audio_duration = audio_clip.duration
    print(f"Audio duration: {audio_duration} seconds")

    image_clips_data = transcript_data['image_clips_data']
    target_duration = transcript_data['duration']

    print(f"Processing {len(image_clips_data)} image clips with variable timing...")
    print(f"Target video duration: {target_duration} seconds")

    # Generate each image and create video clips with proper timing
    generated_clips = []
    fps = 30
    clip_count = len(image_clips_data)
    for i in range(clip_count):
        clip_data = image_clips_data[i]
        print(f"=== Generating image {i + 1}/{clip_count} ===")
        print(f"Clip text: {clip_data['text']}")
        print(f"Clip timing: {clip_data['start_time']:.2f}s - {clip_data['end_time']:.2f}s ({clip_data['duration']:.2f}s)")
        print(f"Image prompt: {clip_data['image_prompt'][:100]}...")

        try:
            # Generate image using FLUX
            print(f"Generating image for clip {i + 1}")
            image = pipe(
                prompt=clip_data['image_prompt'],
                negative_prompt=clip_data['image_negative_prompt'],
                height=1080,
                width=1080,
                num_inference_steps=20,
                guidance_scale=3.5,
            ).images[0]

            print(f"Generated image for clip {i + 1}")

            # Save image temporarily
            temp_image_path = f"/tmp/image_{i}.png"
            image.save(temp_image_path)
            print(f"Image {i + 1} saved to: {temp_image_path}")

            print("=== Uploading clip images of video to S3 ===")
            image_key = f"images/{video_id}_image_{i}.png"
            s3_client.upload_file(
                temp_image_path,
                s3_bucket,
                image_key,
                ExtraArgs={'ContentType': 'image/png'}
            )
            print(f"Clip image uploaded to: {image_key}")

            is_last = i == clip_count - 1
            # Create video clip from static image with exact timing from voiceover
            clip_duration = clip_data['duration'] if is_last != True else clip_data['duration'] + 2
            video_clip = ImageClip(temp_image_path, duration=clip_duration)

            # Apply subtle zoom effect for more dynamic feel
            zoom_factor = 1.05
            video_clip = video_clip.resized(lambda t: 1 + (zoom_factor - 1) * t / clip_duration)

            # Set the start time for this clip to match voiceover timing
            video_clip = video_clip.with_start(clip_data['start_time'])

            print(
                f"Created video clip from image {i + 1} with timing {clip_data['start_time']:.2f}-{clip_data['end_time']:.2f}")

            # Create synchronized captions using absolute timing
            print(f"Creating synchronized captions for clip {i + 1}")
            text_clips = create_captions(clip_data)
            print(f"Created {len(text_clips)} caption segments for clip {i + 1}")

            # Composite video with synchronized text
            if text_clips:
                video_clip = CompositeVideoClip([video_clip] + text_clips)

            generated_clips.append(video_clip)
            print(f"Clip {i + 1} processed successfully")

        except Exception as e:
            print(f"✗ Error generating image for clip {i + 1}: {str(e)}")
            # Create a fallback clip (solid color with text) with proper timing
            fallback_clip = (
                ColorClip(
                    size=(1080, 1080),
                    color=(50, 50, 50),
                    duration=clip_data['duration']
                )
                .with_start(clip_data['start_time'])
                .with_effects([
                    TextClip(
                        text=clip_data['text'],
                        font_size=24,
                        color='white'
                    ).with_position("center")
                ])
            )
            generated_clips.append(fallback_clip)
            print(f"Using fallback clip for segment {i + 1}")

    print(f"Generated all {len(generated_clips)} video clips")

    # Create composite video with all clips at their proper timing
    print("=== Creating composite video with synchronized timing ===")
    final_video = CompositeVideoClip(generated_clips, size=(1080, 1080))

    # Set total duration to match audio
    final_video = final_video.with_duration(target_duration)
    print(f"Video clips composited, total duration: {final_video.duration:.2f} seconds")

    # Add audio track to video
    print("=== Adding audio track ===")
    final_video = final_video.with_audio(audio_clip)

    # Export final video
    print("=== Exporting final video ===")
    final_video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=fps,
        preset='medium',
        bitrate='2000k'
    )
    print("Final video exported successfully")


def process_video_job(job_data):
    print("=== RunPod Handler Started ===")
    print(f"Job: {json.dumps(job_data, indent=2)}")

    s3_bucket = job_data["s3_bucket"]
    transcript_key = job_data["transcript_key"]
    audio_key = job_data["audio_key"]
    video_id = job_data["video_id"]

    print(f"S3 Bucket: {s3_bucket}")
    print(f"Transcript Key: {transcript_key}")
    print(f"Audio Key: {audio_key}")
    print(f"Video ID: {video_id}")

    try:
        print("=== Downloading transcript from S3 ===")
        transcript_response = s3_client.get_object(Bucket=s3_bucket, Key=transcript_key)
        transcript_data = json.loads(transcript_response['Body'].read())
        print(f"Transcript downloaded with {transcript_data.get('clip_count', 'unknown')} clips")

        print("=== Downloading audio from S3 ===")
        audio_local_path = f"/tmp/{video_id}_audio.mp3"
        s3_client.download_file(s3_bucket, audio_key, audio_local_path)
        audio_size = os.path.getsize(audio_local_path)
        print(f"Audio downloaded: {audio_size} bytes")

        # Generate video using image-based approach with synchronized timing
        print("=== Starting synchronized image-based video generation ===")
        output_video_path = f"/tmp/{video_id}_final.mp4"
        generate_video_from_images(transcript_data, audio_local_path, output_video_path, s3_bucket, video_id)

        video_size = os.path.getsize(output_video_path)
        print(f"Video generated: {video_size} bytes")

        print("=== Uploading final video to S3 ===")
        video_key = f"videos/{video_id}.mp4"
        s3_client.upload_file(
            output_video_path,
            s3_bucket,
            video_key,
            ExtraArgs={'ContentType': 'video/mp4'}
        )
        print(f"Video uploaded to: {video_key}")
        print(f"=== VIDEO GENERATION COMPLETED SUCCESSFULLY ===")

        return {
            "success": True,
            "video_id": video_id,
            "video_key": video_key,
            "duration": transcript_data['duration'],
            "clip_count": transcript_data['clip_count']
        }

    except Exception as e:
        error_msg = f"Error during video generation: {str(e)}"
        print(f"✗ {error_msg}")
        print(f"Traceback: {traceback.format_exc()}")

        try:
            error_metadata = {
                'video_id': video_id,
                'status': 'error',
                'error': str(e),
                'exception_type': type(e).__name__
            }

            error_key = f"errors/{video_id}_error.json"
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=error_key,
                Body=json.dumps(error_metadata, indent=2),
                ContentType='application/json'
            )
            print(f"Error metadata uploaded: {error_key}")
        except Exception as meta_error:
            print(f"✗ Failed to upload error metadata: {str(meta_error)}")

        return {
            "success": False,
            "video_id": video_id,
            "error": str(e)
        }
    finally:
        stop_pod()


def stop_pod():
    try:
        print("=== Stopping RunPod instance ===")
        RUNPOD_POD_ID = os.getenv('STOPPING_RUNPOD_POD_ID')
        RUNPOD_API_KEY = os.getenv('STOPPING_RUNPOD_API_KEY')

        if RUNPOD_POD_ID and RUNPOD_API_KEY:
            stop_url = f"https://rest.runpod.io/v1/pods/{RUNPOD_POD_ID}/stop"
            headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}"}
            response = requests.post(stop_url, headers=headers)
            print(f"Pod stop request sent: {response.status_code}")
        else:
            print("⚠ Missing pod stopping credentials")
    except Exception as e:
        print(f"✗ Error stopping RunPod instance: {str(e)}")


# Flask app setup
app = Flask(__name__)


@app.route('/process', methods=['POST'])
def process_video_async():
    """Endpoint to start video processing asynchronously"""
    try:
        job_data = request.json
        job_id = job_data["video_id"]

        print(f"Received video processing request for job: {job_id}")

        # Start video processing in a separate thread
        thread = threading.Thread(target=process_video_job, args=(job_data,))
        thread.daemon = True  # Dies when main thread dies
        thread.start()

        print(f"Started background processing for job: {job_id}")

        return jsonify({
            "success": True,
            "message": "Video generation process started",
            "job_id": job_id,
            "status": "processing"
        }), 202  # HTTP 202 Accepted

    except Exception as e:
        print(f"✗ Failed to start video processing: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "synchronized-video-generator",
        "model": "FLUX.1-dev"
    })


if __name__ == "__main__":
    print("Starting synchronized video generator service...")
    print("=== Initializing S3 client ===")
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION')
    )
    print("S3 client initialized")
    app.run(host='0.0.0.0', port=8000, threaded=True)