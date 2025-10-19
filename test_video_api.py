"""
Test script for video generation API.

This script tests all 4 video generation modes:
1. Text to video
2. Frames to video
3. References to video
4. Extend video
"""
import requests
import base64
import os
from PIL import Image
from io import BytesIO

BASE_URL = "http://localhost:8000"


def create_test_image(color=(255, 0, 0), size=(512, 512)):
    """Create a simple test image and return base64 encoded data."""
    img = Image.new('RGB', size, color=color)
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()
    return base64.b64encode(image_bytes).decode('utf-8')


def test_text_to_video(token):
    """Test text-to-video generation."""
    print("\n" + "="*60)
    print("TEST 1: Text to Video")
    print("="*60)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "prompt": "A serene lake at sunset with mountains in the background",
        "model": "veo-3.1-fast-generate-preview",
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "mode": "text_to_video"
    }
    
    print(f"Sending request: {payload['prompt']}")
    response = requests.post(
        f"{BASE_URL}/api/videos/generate",
        json=payload,
        headers=headers,
        timeout=600  # 10 minute timeout for video generation
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Success!")
        print(f"  Video URL: {result['video_url']}")
        print(f"  Video URI: {result['video_uri'][:50]}...")
        print(f"  Message: {result['message']}")
        return result['video_uri']
    else:
        print(f"✗ Failed: {response.status_code}")
        print(f"  Error: {response.text}")
        return None


def test_frames_to_video(token):
    """Test frames-to-video generation."""
    print("\n" + "="*60)
    print("TEST 2: Frames to Video")
    print("="*60)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create test frames
    start_frame_data = create_test_image(color=(255, 0, 0))  # Red
    end_frame_data = create_test_image(color=(0, 0, 255))    # Blue
    
    payload = {
        "prompt": "Smooth color transition from red to blue",
        "model": "veo-3.1-fast-generate-preview",
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "mode": "frames_to_video",
        "start_frame": {
            "mime_type": "image/png",
            "data": start_frame_data
        },
        "end_frame": {
            "mime_type": "image/png",
            "data": end_frame_data
        }
    }
    
    print(f"Sending request with start and end frames")
    response = requests.post(
        f"{BASE_URL}/api/videos/generate",
        json=payload,
        headers=headers,
        timeout=600
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Success!")
        print(f"  Video URL: {result['video_url']}")
        print(f"  Message: {result['message']}")
    else:
        print(f"✗ Failed: {response.status_code}")
        print(f"  Error: {response.text}")


def test_references_to_video(token):
    """Test references-to-video generation."""
    print("\n" + "="*60)
    print("TEST 3: References to Video")
    print("="*60)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create test reference images
    reference_data = create_test_image(color=(0, 255, 0))  # Green
    style_data = create_test_image(color=(255, 255, 0))    # Yellow
    
    payload = {
        "prompt": "Create a video with these reference elements",
        "model": "veo-3.1-fast-generate-preview",
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "mode": "references_to_video",
        "reference_images": [
            {
                "mime_type": "image/png",
                "data": reference_data
            }
        ],
        "style_image": {
            "mime_type": "image/png",
            "data": style_data
        }
    }
    
    print(f"Sending request with reference and style images")
    response = requests.post(
        f"{BASE_URL}/api/videos/generate",
        json=payload,
        headers=headers,
        timeout=600
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Success!")
        print(f"  Video URL: {result['video_url']}")
        print(f"  Message: {result['message']}")
    else:
        print(f"✗ Failed: {response.status_code}")
        print(f"  Error: {response.text}")


def test_extend_video(token, video_uri):
    """Test extend-video generation."""
    print("\n" + "="*60)
    print("TEST 4: Extend Video")
    print("="*60)
    
    if not video_uri:
        print("✗ Skipped: No video URI from previous test")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "prompt": "Continue the scene with more dramatic elements",
        "model": "veo-3.1-fast-generate-preview",
        "resolution": "720p",
        "mode": "extend_video",
        "input_video": {
            "uri": video_uri
        }
    }
    
    print(f"Sending request to extend video")
    response = requests.post(
        f"{BASE_URL}/api/videos/generate",
        json=payload,
        headers=headers,
        timeout=600
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Success!")
        print(f"  Video URL: {result['video_url']}")
        print(f"  Message: {result['message']}")
    else:
        print(f"✗ Failed: {response.status_code}")
        print(f"  Error: {response.text}")


def main():
    """Main test function."""
    print("="*60)
    print("Video Generation API Test Suite")
    print("="*60)
    
    # Login first
    username = input("Username (or press Enter for 'test'): ").strip() or "test"
    password = input("Password (or press Enter for 'test'): ").strip() or "test"
    
    print("\nLogging in...")
    login_response = requests.post(
        f"{BASE_URL}/api/login",
        json={"username": username, "password": password}
    )
    
    if login_response.status_code != 200:
        print(f"✗ Login failed: {login_response.status_code}")
        print(f"  Error: {login_response.text}")
        return
    
    token = login_response.json()["access_token"]
    print("✓ Login successful")
    
    # Run tests
    print("\nNote: Each video generation can take 2-5 minutes...")
    print("You can press Ctrl+C to skip a test\n")
    
    video_uri = None
    
    try:
        video_uri = test_text_to_video(token)
    except KeyboardInterrupt:
        print("\n✗ Test skipped by user")
    except requests.exceptions.Timeout:
        print("\n✗ Test timed out")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
    
    try:
        test_frames_to_video(token)
    except KeyboardInterrupt:
        print("\n✗ Test skipped by user")
    except requests.exceptions.Timeout:
        print("\n✗ Test timed out")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
    
    try:
        test_references_to_video(token)
    except KeyboardInterrupt:
        print("\n✗ Test skipped by user")
    except requests.exceptions.Timeout:
        print("\n✗ Test timed out")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
    
    try:
        test_extend_video(token, video_uri)
    except KeyboardInterrupt:
        print("\n✗ Test skipped by user")
    except requests.exceptions.Timeout:
        print("\n✗ Test timed out")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
    
    print("\n" + "="*60)
    print("Test suite completed!")
    print("="*60)


if __name__ == "__main__":
    main()

