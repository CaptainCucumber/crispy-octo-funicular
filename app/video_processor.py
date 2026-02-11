from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

import cv2
import requests
from PIL import Image

from app.config import Config

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Handles Instagram Reels video download and frame extraction."""

    def __init__(self, config: Config):
        self.config = config
        self.instagram_access_token = config.instagram_access_token
        self.frame_interval = 2  # Extract 1 frame per 2 seconds
        self.max_video_size = 100 * 1024 * 1024  # 100MB limit for Cloud Run
        self.max_frames = 10  # Limit frames for memory efficiency

    def download_video(self, video_url: str) -> Optional[bytes]:
        """
        Download video from Instagram using the Basic Display API.
        Checks file size before downloading to avoid exceeding 100MB limit.
        
        Args:
            video_url: The URL of the Instagram Reel video
            
        Returns:
            Video content as bytes, or None if download fails or exceeds size limit
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.instagram_access_token}",
                "User-Agent": "Mozilla/5.0 (compatible; InstagramBot/1.0)",
            }
            
            # First, make a HEAD request to check content length
            head_response = requests.head(video_url, headers=headers, timeout=10)
            content_length = int(head_response.headers.get('content-length', 0))
            
            if content_length > self.max_video_size:
                logger.error(
                    "video.too_large",
                    extra={"size": content_length, "max_size": self.max_video_size, "url": video_url}
                )
                return None
            
            # Now download the video with size checking
            response = requests.get(video_url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()
            
            video_content = b""
            downloaded = 0
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > self.max_video_size:
                        logger.error(
                            "video.size_exceeded_during_download",
                            extra={"downloaded": downloaded, "max_size": self.max_video_size}
                        )
                        return None
                    video_content += chunk
                    
            logger.info("video.downloaded", extra={"video_size": len(video_content)})
            return video_content
            
        except Exception as e:
            logger.exception("video.download_failed", extra={"error": str(e), "url": video_url})
            return None

    def extract_frames(self, video_content: bytes) -> List[bytes]:
        """
        Extract frames from video at specified intervals.
        Ensures temp file cleanup and memory release after processing.
        
        Args:
            video_content: Video content as bytes
            
        Returns:
            List of frame images as bytes (JPEG format), max 10 frames
        """
        frames = []
        temp_video_path = None
        
        try:
            # Write video to temporary file
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
                temp_video.write(video_content)
                temp_video_path = temp_video.name
            
            try:
                # Open video with OpenCV
                cap = cv2.VideoCapture(temp_video_path)
                if not cap.isOpened():
                    logger.error("video.open_failed", extra={"path": temp_video_path})
                    return frames
                
                fps = cap.get(cv2.CAP_PROP_FPS)
                if fps <= 0:
                    fps = 30  # Default to 30 FPS if unable to detect
                
                frame_interval_count = int(fps * self.frame_interval)
                frame_count = 0
                extracted_count = 0
                
                while extracted_count < self.max_frames:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # Extract frame at specified interval
                    if frame_count % frame_interval_count == 0:
                        # Convert BGR to RGB
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        
                        # Convert to PIL Image
                        pil_image = Image.fromarray(frame_rgb)
                        
                        # Resize if too large (max 1024px on longest side)
                        max_size = 1024
                        if max(pil_image.size) > max_size:
                            ratio = max_size / max(pil_image.size)
                            new_size = tuple(int(dim * ratio) for dim in pil_image.size)
                            pil_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)
                        
                        # Convert to JPEG bytes
                        img_byte_arr = io.BytesIO()
                        pil_image.save(img_byte_arr, format="JPEG", quality=85)
                        frames.append(img_byte_arr.getvalue())
                        extracted_count += 1
                    
                    frame_count += 1
                
                cap.release()
                logger.info(
                    "video.frames_extracted",
                    extra={
                        "total_frames": frame_count,
                        "extracted_frames": extracted_count,
                        "fps": fps,
                    },
                )
                
            finally:
                # Clean up temporary file immediately to free memory
                if temp_video_path and os.path.exists(temp_video_path):
                    try:
                        os.unlink(temp_video_path)
                        logger.debug("video.temp_file_deleted", extra={"path": temp_video_path})
                    except Exception as cleanup_error:
                        logger.warning(
                            "video.cleanup_failed",
                            extra={"error": str(cleanup_error), "path": temp_video_path}
                        )
                    
        except Exception as e:
            logger.exception("video.frame_extraction_failed", extra={"error": str(e)})
        finally:
            # Ensure cleanup even if exception occurred
            if temp_video_path and os.path.exists(temp_video_path):
                try:
                    os.unlink(temp_video_path)
                except:
                    pass
            
        return frames

    def get_media_info(self, media_id: str) -> Optional[Dict[str, Any]]:
        """
        Get media information from Instagram Basic Display API.
        
        Args:
            media_id: Instagram media ID
            
        Returns:
            Dictionary containing media information including video URL
        """
        try:
            url = f"https://graph.instagram.com/{media_id}"
            params = {
                "fields": "id,media_type,media_url,permalink,timestamp,caption",
                "access_token": self.instagram_access_token,
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            media_info = response.json()
            logger.info("instagram.media_info_retrieved", extra={"media_id": media_id})
            return media_info
            
        except Exception as e:
            logger.exception(
                "instagram.media_info_failed",
                extra={"error": str(e), "media_id": media_id},
            )
            return None

    def process_video_url(self, video_url: str) -> Optional[List[bytes]]:
        """
        Download video and extract frames in one operation.
        
        Args:
            video_url: URL of the video to process
            
        Returns:
            List of extracted frame images as bytes
        """
        video_content = self.download_video(video_url)
        if not video_content:
            return None
            
        frames = self.extract_frames(video_content)
        return frames if frames else None

    def process_media_id(self, media_id: str) -> Optional[List[bytes]]:
        """
        Process Instagram media by ID - get info and extract frames.
        
        Args:
            media_id: Instagram media ID
            
        Returns:
            List of extracted frame images as bytes
        """
        media_info = self.get_media_info(media_id)
        if not media_info:
            return None
            
        media_type = media_info.get("media_type")
        if media_type != "VIDEO":
            logger.warning(
                "instagram.not_video",
                extra={"media_id": media_id, "media_type": media_type},
            )
            return None
            
        video_url = media_info.get("media_url")
        if not video_url:
            logger.error("instagram.no_video_url", extra={"media_id": media_id})
            return None
            
        return self.process_video_url(video_url)


def encode_frame_to_base64(frame_bytes: bytes) -> str:
    """
    Encode frame bytes to base64 string for AI analysis.
    
    Args:
        frame_bytes: Frame image as bytes
        
    Returns:
        Base64 encoded string
    """
    return base64.b64encode(frame_bytes).decode("utf-8")
