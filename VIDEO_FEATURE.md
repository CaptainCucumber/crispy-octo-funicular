# Instagram Reels Video Processing Feature

## Overview

This feature enables the bot to process Instagram Reels videos by downloading them, extracting frames, and using AI to analyze the content and generate contextual comments.

## How It Works

1. **Video Detection**: When a video message is received via Telegram, the system detects it and initiates video processing.

2. **Frame Extraction**: The video is processed to extract frames at 2-second intervals using OpenCV.

3. **AI Analysis**: Extracted frames are sent to OpenAI's Vision API (GPT-4o) to analyze the video content, understanding:
   - Main subjects and actions
   - Video setting and environment
   - Overall theme and context
   - Any text or captions present

4. **Comment Generation**: Based on the video analysis and the bot's learned communication style, an appropriate comment is generated using GPT-4o-mini.

5. **Response**: The generated comment is posted back to the Telegram chat.

## Setup

### 1. Instagram Basic Display API

To use this feature, you need to set up Instagram Basic Display API access:

1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Create a new app or use an existing one
3. Add "Instagram Basic Display" product
4. Configure OAuth settings and get your access token
5. Set the `INSTAGRAM_ACCESS_TOKEN` environment variable

### 2. Environment Variables

Add the following to your `.env` file or deployment environment:

```bash
# Instagram API (optional - only needed for Instagram Reels processing)
INSTAGRAM_ACCESS_TOKEN=your_instagram_access_token_here

# OpenAI Models (optional - defaults provided)
OPENAI_MODEL=gpt-4o-mini              # For text generation
OPENAI_VISION_MODEL=gpt-4o            # For video frame analysis
```

### 3. Dependencies

The following packages are required and included in `requirements.txt`:

```
opencv-python==4.10.0.84
pillow==10.4.0
```

Install with:
```bash
pip install -r requirements.txt
```

## Architecture

### New Module: `video_processor.py`

- `VideoProcessor`: Main class for handling video operations
  - `download_video()`: Downloads video from URL
  - `extract_frames()`: Extracts frames at 2-second intervals
  - `process_video_url()`: Complete pipeline for URL-based videos
  - `process_media_id()`: Process Instagram media by ID
  - `get_media_info()`: Retrieve media information from Instagram API

### Enhanced AI Adapter: `ai_adapter.py`

New functions added:
- `analyze_video_frames()`: Analyzes video frames using GPT-4o Vision API
- `generate_video_comment()`: Generates contextual comments based on video analysis

### Updated Message Processor: `message_processor.py`

- Modified `process_update()` to detect video messages
- Added `_process_video_message()`: Handles complete video processing workflow
- Added `_get_telegram_file_url()`: Retrieves video download URLs from Telegram

## Usage

### Processing Telegram Videos

When a video is sent to the bot via Telegram:

```python
# Automatically detected and processed
# 1. Video is downloaded from Telegram
# 2. Frames are extracted every 2 seconds
# 3. AI analyzes the frames
# 4. A comment is generated and posted
```

### Processing Instagram Reels (Direct API)

For direct Instagram integration:

```python
from app.config import get_config
from app.video_processor import VideoProcessor

config = get_config()
processor = VideoProcessor(config)

# Process by media ID
frames = processor.process_media_id("instagram_media_id")

# Or process by direct URL
frames = processor.process_video_url("https://instagram.com/video_url")
```

## Configuration Options

### Frame Extraction

Modify `frame_interval` in `VideoProcessor` class:

```python
self.frame_interval = 2  # Extract 1 frame per 2 seconds
```

### Video Frame Limits

To avoid token limits, the system processes a maximum of 10 frames. Adjust in `ai_adapter.py`:

```python
max_frames = min(len(frames), 10)  # Modify this value
```

### Image Quality

Frame quality can be adjusted in `video_processor.py`:

```python
pil_image.save(img_byte_arr, format="JPEG", quality=85)  # 0-100
```

## API Costs

### OpenAI Vision API
- Model: GPT-4o
- Cost: ~$0.0025 per frame (at "low" detail)
- Per video (10 frames): ~$0.025

### Text Generation
- Model: GPT-4o-mini
- Cost: Minimal (~$0.0001 per comment)

## Limitations

1. **Token Limits**: Maximum 10 frames per video to stay within API token limits
2. **Video Size**: Large videos may take time to download and process
3. **Instagram API**: Requires valid access token with appropriate permissions
4. **Processing Time**: Video analysis can take 30-60 seconds depending on video length

## Error Handling

The system includes comprehensive error handling:

- Failed downloads are logged and skipped
- Frame extraction errors are caught and logged
- AI analysis failures are handled gracefully
- Telegram API errors are properly managed

All errors are logged with structured context for debugging.

## Testing

To test the video processing feature:

1. Send a video to your Telegram bot
2. Check logs for processing status
3. Verify the AI-generated comment is posted

## Future Enhancements

Potential improvements:
- Support for multiple video sources (YouTube, TikTok, etc.)
- Audio transcription and analysis
- Scene detection for more intelligent frame selection
- Batch processing for multiple videos
- Video metadata extraction and analysis
- Custom frame extraction strategies based on video content
