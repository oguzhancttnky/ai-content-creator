import json
import os
import time
import boto3
import requests
from datetime import datetime, timezone
import re
import random
import uuid

def clean_text(text):
    return re.sub(r'[^\w\s.,?!:\']', '', text)  # \w = letters/numbers, \s = whitespace characters, .,?!:' are allowed

def find_string_timestamps(word_timestamps, target_string):
    target_words = target_string.split()
    n = len(target_words)
    for i in range(len(word_timestamps) - n + 1):
        candidate_words = [w['word'] for w in word_timestamps[i:i + n]]
        if candidate_words == target_words:
            clip_word_timestamps = word_timestamps[i:i + n]
            return word_timestamps[i]['start'], word_timestamps[i + n - 1]['end'], clip_word_timestamps

    return None, None, None

def get_random_story():
    url = "https://shortstories-api.onrender.com/"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return clean_text(data["title"]), clean_text(data["story"]), clean_text(data["moral"])
    else:
        print(f"Error: Received status code {response.status_code}")
        raise Exception("Failed to fetch example story from API")


def lambda_handler(event, context):
    try:
        print("=== Lambda function started ===")
        print(f"Event: {json.dumps(event)}")
        print(f"Context: {context}")

        DEEPSEEK_API_KEY = os.environ['DEEPSEEK_API_KEY']
        ELEVENLABS_API_KEY = os.environ['ELEVENLABS_API_KEY']
        S3_BUCKET = os.environ['S3_BUCKET']
        RUNPOD_API_KEY = os.environ['RUNPOD_API_KEY']
        RUNPOD_POD_ID = os.environ['RUNPOD_POD_ID']
        print("✓ All environment variables loaded successfully")

        s3_client = boto3.client('s3')
        print("✓ S3 client initialized")

        example_title, example_story, example_moral = get_random_story()
        if not example_title or not example_story or not example_moral:
            print("✗ Failed to fetch example story from API")
            raise Exception("No valid example story received from API")

        # Generate content using Deepseek API
        print("=== Starting Deepseek API call for content generation ===")
        deepseek_url = "https://api.deepseek.com/v1/chat/completions"
        deepseek_headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }

        story_duration = random.randrange(32,61, 4)
        clip_count = story_duration / 4
        clip_word_count = 10 # the average speaking speed is 2.5 wps and each clip 4 seconds long
        total_word_count = clip_word_count * clip_count

        deepseek_payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a world-class viral content creator known for crafting powerful short-form video stories that captivate millions. "
                        "Your work blends storytelling psychology, viral dynamics, and cinematic visuals to produce unforgettable narratives. "

                        "TASK:\n"
                        f"Generate a {story_duration}-second video script tailored for TikTok, YouTube Shorts, and Instagram Reels. "
                        f"Each video contains {clip_count} clips, each synced to 4 seconds of voiceover (~{clip_word_count} words per clip). "
                        f"Total word count must be exactly {total_word_count} words for perfect timing. DO NOT EXCEED THIS LIMIT.\n"

                        "FORMAT:\n"
                        "Return ONLY valid JSON (no markdown or code blocks) with these exact keys:\n"
                        "- title (string): A gripping curiosity-driven title\n"
                        "- description (string): A punchy share-worthy description\n"
                        "- hashtags (array): 10 lowercase viral hashtags (no # symbol)\n"
                        f"- clip_texts (array): {clip_count} strings of exactly {clip_word_count} words each, one per video clip\n"

                        "INSPIRATION EXAMPLE:\n"
                        f"Title: {example_title}\n"
                        f"Story: {example_story}\n"
                        f"Moral: {example_moral}\n"

                        "CONTENT STRATEGY:\n"
                        "- Use present tense to create urgency and energy\n"
                        "- Start with an immediate emotional hook\n"
                        "- Use specificity: names, dates, places, unusual facts\n"
                        "- Avoid clichés, be unpredictable and bold\n"
                        "- Each clip must describe a visually distinct and vivid scene\n"
                        "- Build tension gradually and deliver a surprising payoff"

                        "CLIP STRUCTURE:\n"
                        "Clip 0-1: Instant hook and dramatic setup\n"
                        "Clip 2-4: Rising action with intrigue or mystery\n"
                        "Clip 5-7: Shocking twist or revealing detail\n"
                        "Clip 8-9: Emotional climax and satisfying resolution\n"

                        "VISUAL AND EMOTIONAL GUIDANCE:\n"
                        "- Each scene must be easy to imagine and emotionally resonant\n"
                        "- Include concrete visuals: people, actions, environments\n"
                        "- Use emotional triggers: betrayal, revenge, redemption, irony, awe\n"
                        "- Aim for contrast between clips for visual interest\n"

                        "ENGAGEMENT TIPS:\n"
                        "- Create story gaps that hook the viewer's curiosity\n"
                        "- Avoid overused tropes (lost pets, cheating lovers, generic advice)\n"
                        "- No abstract ideas, technical jargon, or complex science\n"
                        "- Avoid political or religious content\n"
                        "- No promotional, salesy, or motivational fluff\n"
                        "- Avoid special characters (!, *, ~, #, etc.) — use plain punctuation\n"

                        "Remember: this is not just a story — it’s a *viral video experience*. "
                        "Every line should invite curiosity, spark imagination, and emotionally compel the viewer to watch until the end — and then share it."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Create a {story_duration}-second story-based video script for virality. "
                        f"The story will use {clip_count} sequential images, each with {clip_word_count} words of narration. "
                        "Ensure the story builds steadily and delivers a strong emotional or ironic payoff. "
                        "Each clip should feel like a visually distinct cinematic shot. Focus on emotional tension, narrative pacing, and viewer engagement."
                    )
                }
            ],
            "max_tokens": 1200,
            "temperature": 0.85,
            "top_p": 0.95,
            "frequency_penalty": 0.4,
            "presence_penalty": 0.6
        }

        print(f"Deepseek payload: {json.dumps(deepseek_payload, indent=2)}")
        deepseek_response = requests.post(deepseek_url, headers=deepseek_headers, json=deepseek_payload)
        print(f"Deepseek response status: {deepseek_response.status_code}")
        print(f"Deepseek response headers: {deepseek_response.headers}")
        deepseek_response.raise_for_status()

        deepseek_json = deepseek_response.json()
        print(f"Deepseek response: {json.dumps(deepseek_json, indent=2)}")

        # Extract content and clean markdown formatting
        raw_content = deepseek_json['choices'][0]['message']['content']
        print(f"Raw content: {raw_content}")

        # Remove markdown code blocks if present
        if raw_content.strip().startswith('```json'):
            json_start = raw_content.find('```json') + 7
            json_end = raw_content.rfind('```')
            json_content = raw_content[json_start:json_end].strip()
        elif raw_content.strip().startswith('```'):
            json_start = raw_content.find('```') + 3
            json_end = raw_content.rfind('```')
            json_content = raw_content[json_start:json_end].strip()
        else:
            json_content = raw_content.strip()

        print(f"Cleaned JSON content: {json_content}")

        try:
            content_data = json.loads(json_content)
            print(f"Parsed content data: {json.dumps(content_data, indent=2)}")
        except json.JSONDecodeError as json_err:
            print(f"✗ JSON parsing error: {str(json_err)}")
            print(f"Attempting to fix common JSON issues...")

            fixed_json = json_content.replace('\n', ' ').replace('\t', ' ')
            fixed_json = re.sub(r'\s+', ' ', fixed_json)

            try:
                content_data = json.loads(fixed_json)
                print(f"✓ JSON parsed after fixing: {json.dumps(content_data, indent=2)}")
            except json.JSONDecodeError:
                print(f"✗ Could not parse JSON even after fixes")
                raise json_err

        # Clean script text of Unicode characters
        script_text = ""
        for i in range(len(content_data['clip_texts'])):
            text = clean_text(content_data['clip_texts'][i]).strip("'")
            content_data['clip_texts'][i] = text
            if i == 0:
                script_text += text
            else:
                script_text += " " + text
        print(f"Cleaned script text: {script_text}")
        print(f"Script text length: {len(script_text)} characters")
        print("✓ Deepseek API call completed successfully")
        voices = [
                "ZF6FPAbjXT4488VcRRnw", "8JVbfL6oEdmuxKn5DK2C","iCrDUkL56s3C8sCRl7wb", "1hlpeD1ydbI2ow0Tt3EW",
                "EkK5I93UQWFDigLMpZcX", "EiNlNiXeDU1pqqOPrYMO", "AeRdCCKzvd23BpJoofzx", "xTZlmU8dKXdyk4XGYGFg",
                "0lp4RIz96WD1RUtvEu3Q", "oQV06a7Gn8pbCJh5DXcO", "j9jfwdrw7BRfcR43Qohk", "Mu5jxyqZOLIGltFpfalg",
                "aEO01A4wXwd1O8GPgGlF", "FVQMzxJGPUBtfz1Azdoy", "gOkFV1JMCt0G0n9xmBwV", "alMSnmMfBQWEfTP8MRcX"
              ]
        random_id = random.choice(voices)
        # Generate voiceover with timestamps using ElevenLabs
        print("=== Starting ElevenLabs API call with timestamps ===")
        alignment_url = f"https://api.elevenlabs.io/v1/text-to-speech/{random_id}/with-timestamps"
        elevenlabs_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }

        elevenlabs_payload = {
            "text": script_text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.5,
                "use_speaker_boost": True
            }
        }

        print(f"ElevenLabs alignment URL: {alignment_url}")
        print(f"ElevenLabs payload: {json.dumps({**elevenlabs_payload, 'text': f'{script_text[:100]}...'}, indent=2)}")

        alignment_response = requests.post(alignment_url, headers=elevenlabs_headers, json=elevenlabs_payload)
        print(f"ElevenLabs alignment response status: {alignment_response.status_code}")
        print(f"ElevenLabs alignment response headers: {alignment_response.headers}")

        alignment_data = alignment_response.json()

        # Get the audio content
        audio_content = alignment_data.get('audio_base64')
        if audio_content:
            import base64
            audio_bytes = base64.b64decode(audio_content)
            print(f"✓ Audio content received: {len(audio_bytes)} bytes")
        else:
            raise Exception("No audio content received from ElevenLabs alignment API")

        # Process alignment data to create word-level timestamps
        alignment = alignment_data.get('alignment', {})
        characters = alignment.get('characters', [])
        char_start_times = alignment.get('character_start_times_seconds', [])
        char_end_times = alignment.get('character_end_times_seconds', [])
        audio_duration = char_end_times[-1] if char_end_times else 0
        print(f"✓ Audio duration: {audio_duration} seconds")

        print(f"✓ Alignment data: {len(characters)} characters with timestamps")

        # Create word-level timestamps for video text overlays
        word_timestamps = []
        current_word = ""
        word_start_time = None

        for i, (char, start_time, end_time) in enumerate(zip(characters, char_start_times, char_end_times)):
            if char == ' ' or i == len(characters) - 1:
                if current_word.strip():
                    current_word += char if i == len(characters) - 1 else ""
                    word_timestamps.append({
                        "word": current_word.strip(),
                        "start": word_start_time,
                        "end": end_time
                    })
                current_word = ""
                word_start_time = None
            else:
                if word_start_time is None:
                    word_start_time = start_time
                current_word += char

        print(f"✓ Created {len(word_timestamps)} word timestamps")

        # Generate video prompts for each clip using Deepseek
        print("=== Generating image prompts for clips ===")
        image_clips_data = []
        title = content_data['title']
        description = content_data['description']

        for clip_index, clip_text in enumerate(content_data['clip_texts']):
            clip_prompt_payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a top-tier prompt engineer for FLUX.1-dev, an open-source text-to-image model. "
                            "Your job is to craft cinematic, ultra-detailed, and technically optimized prompts for maximum social media impact.\n\n"
        
                            "**OUTPUT FORMAT**:\n"
                            "- Return ONLY valid JSON with:\n"
                            "  - `image_prompt`: (string) detailed image generation prompt\n"
                            "  - `image_negative_prompt`: (string) exclusions list\n\n"
        
                            "**PROMPT STRUCTURE**:\n"
                            "- Subject\n"
                            "- Action/Pose\n"
                            "- Environment/Setting\n"
                            "- Lighting\n"
                            "- Camera Angle\n"
                            "- Style & Composition\n"
                            "- Technical Specs\n"
                            "- Mood/Atmosphere\n\n"
        
                            "**CREATE A STORY USING THIS EXAMPLE CONTEXT**:\n"
                            f"- Title: \"{title}\"\n"
                            f"- Description: \"{description}\"\n"
                            f"- Full Script: \"{script_text}\"\n\n"
                
                            "**VISUAL CONSISTENCY RULES**:\n"
                            "- Maintain character traits (age, clothing, features)\n"
                            "- Use a consistent color palette across scenes\n"
                            "- Ensure time and light continuity (day/night/weather)\n"
                            "- Keep environment type consistent (indoor/outdoor)\n"
                            "- Use uniform visual style and quality\n\n"
                
                            "**TECHNICAL OPTIMIZATION FOR FLUX.1-dev**:\n"
                            "- Camera terms: \"cinematic wide shot\", \"overhead view\", \"dramatic close-up\"\n"
                            "- Lighting: \"soft diffused light\", \"golden hour\", \"studio spotlight\"\n"
                            "- Specs: \"8K ultra-detailed\", \"hyperrealism\", \"professional photography\"\n"
                            "- Composition: \"rule of thirds\", \"leading lines\", \"depth of field\"\n"
                            "- Mood: \"ethereal ambiance\", \"tense atmosphere\", \"emotional resonance\"\n\n"
                
                            "**MOBILE-FIRST COMPOSITION TIPS**:\n"
                            "- Vertical or square (9:16 / 1:1)\n"
                            "- Single strong focal point\n"
                            "- Bold, high-contrast visuals\n"
                            "- Minimal background clutter\n\n"
                
                            "**VIRAL IMAGE FACTORS**:\n"
                            "- Contrasting, vibrant colors\n"
                            "- Visual surprises or metaphors\n"
                            "- Emotional storytelling through image alone\n"
                            "- Symbolism that grabs attention\n\n"
                
                            "**STYLE & QUALITY ANCHORS** (Always include):\n"
                            "- Camera: \"Shot on RED Komodo / Sony FX3 / Canon R5\"\n"
                            "- Lens: \"85mm f/1.4\" or \"24-70mm f/2.8\"\n"
                            "- Lighting setup: \"natural golden hour\" or \"studio softbox\"\n"
                            "- Color grading: \"cinematic LUT\", \"film emulation\"\n\n"
                
                            "**NEGATIVE PROMPT (Exclude):**\n"
                            "- blurry, low-res, bad anatomy, extra limbs\n"
                            "- watermarks, logos, text, distortions\n"
                            "- cartoonish or amateur styles (unless specified)\n"
                            "- cluttered backgrounds, oversaturation, generic look\n"
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Generate an image prompt for this scene:\n"
                            f"Scene: \"{clip_text}\"\n"
                            f"Scene Position: {clip_index + 1} of {clip_count}\n"
                            f"Narrative Flow: "
                            f"{'Opening hook' if clip_index < 3 else 'Rising action' if clip_index < clip_count * 0.7 else 'Climax/Resolution'}\n\n"
        
                            "REQUIREMENTS:\n"
                            "- Focus on ONE powerful visual moment\n"
                            "- Keep narrative and visual continuity\n"
                            "- Include exact camera and lighting details\n"
                            "- Use a dramatic composition (e.g., rule of thirds, close-up, symmetry)\n"
                            "- Prompt length: 150–250 words, rich in technical detail\n\n"
        
                            "The final image should be so visually compelling it makes viewers stop scrolling and emotionally connect."
                        )
                    }
                ],
                "max_tokens": 1500,
                "temperature": 0.4,
                "top_p": 0.8,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1
            }
            clip_response = requests.post(deepseek_url, headers=deepseek_headers, json=clip_prompt_payload)
            clip_response.raise_for_status()

            clip_json = clip_response.json()
            clip_raw_content = clip_json['choices'][0]['message']['content']

            # Clean markdown formatting
            if clip_raw_content.strip().startswith('```json'):
                json_start = clip_raw_content.find('```json') + 7
                json_end = clip_raw_content.rfind('```')
                clip_json_content = clip_raw_content[json_start:json_end].strip()
            elif clip_raw_content.strip().startswith('```'):
                json_start = clip_raw_content.find('```') + 3
                json_end = clip_raw_content.rfind('```')
                clip_json_content = clip_raw_content[json_start:json_end].strip()
            else:
                clip_json_content = clip_raw_content.strip()

            try:
                clip_prompts = json.loads(clip_json_content)
                start, end, clip_word_timestamps = find_string_timestamps(word_timestamps, clip_text)

                image_clips_data.append({
                    "index": clip_index,
                    "text": clip_text,
                    "start_time": start,
                    "end_time": end,
                    "word_timestamps": clip_word_timestamps,
                    "duration": end - start if start is not None and end is not None else 0,
                    "image_prompt": clip_prompts['image_prompt'],
                    "image_negative_prompt": clip_prompts['image_negative_prompt']
                })
                print(f"✓ Generated prompts for clip {clip_text}")
            except json.JSONDecodeError:
                start, end, clip_word_timestamps = find_string_timestamps(word_timestamps, clip_text)
                # Fallback prompt if parsing fails
                image_clips_data.append({
                    "index": clip_index,
                    "text": clip_text,
                    "start_time": start,
                    "end_time": end,
                    "word_timestamps": clip_word_timestamps,
                    "duration": end - start if start is not None and end is not None else 0,
                    "image_prompt": clip_text,
                    "image_negative_prompt": "blurry, low quality, shaky, irrelevant content"
                })
                print(f"⚠ Used fallback prompt for clip {clip_index}")

        print(f"✓ Generated image prompts for all {len(image_clips_data)} clips")

        # Generate unique ID for this video
        video_id = datetime.now(tz=timezone.utc).strftime("%d_%m_%Y_%H_%M_%S") + "_oguzhancttnky" + str(uuid.uuid4())
        print(f"Generated video_id: {video_id}")

        # Upload transcript with timing data to S3 for video generation
        print("=== Uploading transcript with timestamps to S3 ===")
        transcript_data = {
            "script": script_text,
            "duration": audio_duration,
            "word_count": len(script_text.split()),
            "word_timestamps": word_timestamps,
            "image_clips_data": image_clips_data,
            "clip_count": len(content_data["clip_texts"]),
            "full_alignment": {
                "characters": characters,
                "character_start_times_seconds": char_start_times,
                "character_end_times_seconds": char_end_times
            }
        }
        transcript_key = f"transcripts/{video_id}.json"
        print(f"Transcript S3 key: {transcript_key}")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=transcript_key,
            Body=json.dumps(transcript_data, indent=2),
            ContentType='application/json'
        )
        print("✓ Transcript with timestamps uploaded to S3 successfully")

        # Upload metadata to S3 (complete content data for social media publishing)
        print("=== Uploading metadata to S3 ===")
        metadata_key = f"metadata/{video_id}.json"
        metadata = {
            'video_id': video_id,
            'title': content_data['title'],
            'description': content_data['description'],
            'hashtags': content_data['hashtags'],
            'script': script_text,
            'transcript_key': transcript_key,
            'audio_key': f"audio/{video_id}.mp3",
            'duration': audio_duration,
            'clip_count': len(content_data['clip_texts']),
            'status': 'processing'
        }
        print(f"Metadata S3 key: {metadata_key}")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=metadata_key,
            Body=json.dumps(metadata, indent=2),
            ContentType='application/json'
        )
        print("✓ Metadata uploaded to S3 successfully")

        # Upload MP3 voiceover to S3
        print("=== Uploading MP3 to S3 ===")
        audio_key = f"audio/{video_id}.mp3"
        print(f"Audio S3 key: {audio_key}")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=audio_key,
            Body=audio_bytes,
            ContentType='audio/mpeg'
        )
        print("✓ MP3 uploaded to S3 successfully")

        # Start RunPod instance
        print("=== Starting RunPod instance ===")
        start_url = f"https://rest.runpod.io/v1/pods/{RUNPOD_POD_ID}/start"
        headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}"}
        start_response = requests.post(start_url, headers=headers)
        print(f"Start response: {start_response.status_code}")
        retry_count = 0

        while retry_count < 60:
            if start_response.status_code == 200:
                print("✓ Pod started, waiting for Flask server...")

                runpod_payload = {
                    "s3_bucket": S3_BUCKET,
                    "transcript_key": transcript_key,
                    "audio_key": audio_key,
                    "video_id": video_id,
                }

                flask_url = f"https://{RUNPOD_POD_ID}-8000.proxy.runpod.net/process"
                print(f"Flask URL: {flask_url}")

                print("=== Waiting for pod to start (checking every 10 seconds) ===")

                for i in range(10):  # Check for up to 1.5 minutes
                    # Check pod status
                    status_query = {
                        "query": f"""
                            query {{
                                pod(input: {{podId: "{RUNPOD_POD_ID}"}}) {{
                                    id
                                    name
                                    runtime {{
                                        uptimeInSeconds
                                    }}
                                    desiredStatus
                                    lastStatusChange
                                }}
                            }}
                            """
                    }

                    status_response = requests.post(
                        "https://api.runpod.io/graphql",
                        headers=headers,
                        json=status_query
                    )

                    pod_data = status_response.json().get('data', {}).get('pod', {})
                    runtime = pod_data.get('runtime')

                    print(f"Check {i + 1}: Runtime = {runtime}")

                    if runtime and runtime.get('uptimeInSeconds') is not None:
                        print("✓ Pod is now running!")

                        time.sleep(10)

                        print(f"=== Calling Flask server ===")
                        print(f"URL: {flask_url}")
                        print(f"Payload: {json.dumps(runpod_payload, indent=2)}")

                        try:
                            # Call Flask directly (no Authorization header needed for pod endpoints)
                            response = requests.post(flask_url, json=runpod_payload, timeout=600)  # 10 minute timeout
                            print(f"Flask response status: {response.status_code}")
                            print(f"Flask response: {response.text}")

                            if response.status_code == 200:
                                result = response.json()
                                print(f"✓ Success: {result}")
                                return result
                            else:
                                print(f"✗ Flask error: {response.status_code}")
                                return None

                        except requests.exceptions.Timeout:
                            print("⚠ Request timed out video generation might still be running")
                            return None
                        except Exception as e:
                            print(f"✗ Error calling Flask: {str(e)}")
                            return None
                    else:
                        print(f"Pod still starting... waiting 10 seconds")
                        time.sleep(10)
            else:
                print(f"✗ Failed to start pod: {start_response.text}")
                retry_count += 1
                time.sleep(60)
        return None

    except Exception as e:
        error_msg = f"Error occurred: {str(e)}"
        print(f"✗ {error_msg}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

        error_response = {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_msg,
                'exception_type': type(e).__name__
            })
        }
        print(f"Error response: {json.dumps(error_response, indent=2)}")
        return error_response