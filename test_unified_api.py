"""
Test script for unified generation API.

Tests all modes: TEXT, IMAGE, VIDEO, AUTO
"""
import requests
import base64
import time
import os
from typing import Optional

# Configuration
BASE_URL = "http://localhost:8000"
USERNAME = "testuser"
PASSWORD = "testpass123"

# Test image path (create a simple test image or use existing)
TEST_IMAGE_PATH = "test_image.png"


def create_test_image():
    """Create a simple test image if PIL is available."""
    try:
        from PIL import Image, ImageDraw
        
        # Create a simple 200x200 test image
        img = Image.new('RGB', (200, 200), color='lightblue')
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, 150, 150], fill='darkblue')
        img.save(TEST_IMAGE_PATH)
        print(f"✓ Created test image: {TEST_IMAGE_PATH}")
        return True
    except ImportError:
        print("⚠ PIL not available, skipping image creation")
        return False


def encode_image(image_path: str) -> Optional[dict]:
    """Encode image to base64 format."""
    if not os.path.exists(image_path):
        print(f"⚠ Image not found: {image_path}")
        return None
    
    try:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        # Determine MIME type from extension
        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif'
        }
        mime_type = mime_types.get(ext, 'image/png')
        
        return {
            "mime_type": mime_type,
            "data": image_data
        }
    except Exception as e:
        print(f"✗ Failed to encode image: {e}")
        return None


def get_auth_token() -> Optional[str]:
    """Get authentication token by signing up or logging in."""
    print("\n" + "="*60)
    print("AUTHENTICATION")
    print("="*60)
    
    # Try login first
    try:
        response = requests.post(
            f"{BASE_URL}/api/login",
            json={"username": USERNAME, "password": PASSWORD}
        )
        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"✓ Logged in as {USERNAME}")
            return token
    except Exception:
        pass
    
    # Try signup if login failed
    try:
        response = requests.post(
            f"{BASE_URL}/api/signup",
            json={"username": USERNAME, "password": PASSWORD}
        )
        if response.status_code == 200:
            token = response.json().get("access_token")
            print(f"✓ Signed up as {USERNAME}")
            return token
        else:
            print(f"✗ Signup failed: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        return None


def test_text_mode(token: str, conversation_id: Optional[str] = None):
    """Test TEXT mode."""
    print("\n" + "="*60)
    print("TEST: TEXT MODE")
    print("="*60)
    
    try:
        request_data = {
            "mode": "text",
            "prompt": "Explain what a neural network is in one sentence."
        }
        
        if conversation_id:
            request_data["conversation_id"] = conversation_id
        
        print(f"Request: {request_data}")
        
        response = requests.post(
            f"{BASE_URL}/api/generate-unified",
            headers={"Authorization": f"Bearer {token}"},
            json=request_data,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ TEXT mode successful")
            print(f"  Mode: {result.get('mode')}")
            print(f"  Conversation ID: {result.get('conversation_id')}")
            print(f"  Response: {result.get('text_response', 'N/A')[:200]}...")
            return result.get('conversation_id')
        else:
            print(f"✗ TEXT mode failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
    except Exception as e:
        print(f"✗ TEXT mode error: {e}")
        return None


def test_text_with_image(token: str, image_input: dict):
    """Test TEXT mode with image input."""
    print("\n" + "="*60)
    print("TEST: TEXT MODE WITH IMAGE")
    print("="*60)
    
    try:
        request_data = {
            "mode": "text",
            "prompt": "Describe the colors in this image.",
            "images": [image_input]
        }
        
        print(f"Request: mode=text, prompt with 1 image")
        
        response = requests.post(
            f"{BASE_URL}/api/generate-unified",
            headers={"Authorization": f"Bearer {token}"},
            json=request_data,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ TEXT mode with image successful")
            print(f"  Response: {result.get('text_response', 'N/A')[:200]}...")
            return True
        else:
            print(f"✗ TEXT mode with image failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ TEXT mode with image error: {e}")
        return False


def test_image_mode(token: str, conversation_id: Optional[str] = None):
    """Test IMAGE mode."""
    print("\n" + "="*60)
    print("TEST: IMAGE MODE")
    print("="*60)
    
    try:
        request_data = {
            "mode": "image",
            "prompt": "A cute robot reading a book"
        }
        
        if conversation_id:
            request_data["conversation_id"] = conversation_id
        
        print(f"Request: {request_data}")
        
        response = requests.post(
            f"{BASE_URL}/api/generate-unified",
            headers={"Authorization": f"Bearer {token}"},
            json=request_data,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ IMAGE mode successful")
            print(f"  Mode: {result.get('mode')}")
            print(f"  Conversation ID: {result.get('conversation_id')}")
            print(f"  Assets: {len(result.get('assets', []))} image(s)")
            if result.get('assets'):
                print(f"  First image URL: {result['assets'][0].get('url')}")
            return result.get('conversation_id')
        else:
            print(f"✗ IMAGE mode failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
    except Exception as e:
        print(f"✗ IMAGE mode error: {e}")
        return None


def test_video_text_to_video(token: str):
    """Test VIDEO mode - text_to_video."""
    print("\n" + "="*60)
    print("TEST: VIDEO MODE - TEXT_TO_VIDEO")
    print("="*60)
    print("⚠ This test may take several minutes...")
    
    try:
        request_data = {
            "mode": "video",
            "prompt": "A colorful butterfly flying through a garden",
            "video_mode": "text_to_video",
            "aspect_ratio": "16:9",
            "resolution": "720p",
            "model": "veo-3.1-fast-generate-preview"  # Use fast model for testing
        }
        
        print(f"Request: {request_data}")
        
        response = requests.post(
            f"{BASE_URL}/api/generate-unified",
            headers={"Authorization": f"Bearer {token}"},
            json=request_data,
            timeout=600  # 10 minutes timeout for video generation
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ VIDEO mode (text_to_video) successful")
            print(f"  Mode: {result.get('mode')}")
            print(f"  Video URL: {result.get('video_url')}")
            print(f"  Video URI: {result.get('video_uri', 'N/A')[:60]}...")
            return result.get('video_uri')
        else:
            print(f"✗ VIDEO mode failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
    except Exception as e:
        print(f"✗ VIDEO mode error: {e}")
        return None


def test_video_extend(token: str, video_uri: str):
    """Test VIDEO mode - extend_video."""
    print("\n" + "="*60)
    print("TEST: VIDEO MODE - EXTEND_VIDEO")
    print("="*60)
    print("⚠ This test may take several minutes...")
    
    try:
        request_data = {
            "mode": "video",
            "prompt": "The butterfly lands on a flower",
            "video_mode": "extend_video",
            "input_video": {
                "uri": video_uri
            }
        }
        
        print(f"Request: extending video with URI {video_uri[:60]}...")
        
        response = requests.post(
            f"{BASE_URL}/api/generate-unified",
            headers={"Authorization": f"Bearer {token}"},
            json=request_data,
            timeout=600  # 10 minutes timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ VIDEO mode (extend_video) successful")
            print(f"  Extended video URL: {result.get('video_url')}")
            print(f"  Note: This is the FULL concatenated video (original + extension)")
            return True
        else:
            print(f"✗ VIDEO extend failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ VIDEO extend error: {e}")
        return False


def test_auto_mode_text(token: str):
    """Test AUTO mode with text intent."""
    print("\n" + "="*60)
    print("TEST: AUTO MODE - TEXT INTENT")
    print("="*60)
    
    try:
        request_data = {
            "mode": "auto",
            "prompt": "What is the capital of France?"
        }
        
        print(f"Request: {request_data}")
        
        response = requests.post(
            f"{BASE_URL}/api/generate-unified",
            headers={"Authorization": f"Bearer {token}"},
            json=request_data,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ AUTO mode successful")
            print(f"  Detected mode: {result.get('detected_mode')}")
            print(f"  Actual mode: {result.get('mode')}")
            print(f"  Response: {result.get('text_response', 'N/A')[:200]}...")
            return True
        else:
            print(f"✗ AUTO mode failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ AUTO mode error: {e}")
        return False


def test_auto_mode_image(token: str):
    """Test AUTO mode with image intent."""
    print("\n" + "="*60)
    print("TEST: AUTO MODE - IMAGE INTENT")
    print("="*60)
    
    try:
        request_data = {
            "mode": "auto",
            "prompt": "Create a beautiful painting of a sunset over mountains"
        }
        
        print(f"Request: {request_data}")
        
        response = requests.post(
            f"{BASE_URL}/api/generate-unified",
            headers={"Authorization": f"Bearer {token}"},
            json=request_data,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ AUTO mode successful")
            print(f"  Detected mode: {result.get('detected_mode')}")
            print(f"  Actual mode: {result.get('mode')}")
            if result.get('assets'):
                print(f"  Generated {len(result['assets'])} asset(s)")
            return True
        else:
            print(f"✗ AUTO mode failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ AUTO mode error: {e}")
        return False


def test_conversation_flow(token: str):
    """Test conversation continuity across requests."""
    print("\n" + "="*60)
    print("TEST: CONVERSATION FLOW")
    print("="*60)
    
    # Request 1: Start conversation
    conv_id = test_text_mode(token)
    if not conv_id:
        print("✗ Failed to start conversation")
        return False
    
    time.sleep(1)
    
    # Request 2: Continue conversation
    print("\nContinuing conversation...")
    conv_id_2 = test_text_mode(token, conversation_id=conv_id)
    
    if conv_id_2 == conv_id:
        print(f"✓ Conversation continuity maintained")
        return True
    else:
        print(f"✗ Conversation ID mismatch")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("UNIFIED API TEST SUITE")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    
    # Create test image
    create_test_image()
    
    # Get auth token
    token = get_auth_token()
    if not token:
        print("\n✗ Cannot proceed without authentication")
        return
    
    # Encode test image
    image_input = None
    if os.path.exists(TEST_IMAGE_PATH):
        image_input = encode_image(TEST_IMAGE_PATH)
    
    # Run tests
    results = {
        "Text Mode": test_text_mode(token),
        "Image Mode": test_image_mode(token),
        "Auto Mode (Text)": test_auto_mode_text(token),
        "Auto Mode (Image)": test_auto_mode_image(token),
        "Conversation Flow": test_conversation_flow(token)
    }
    
    # Test with image input if available
    if image_input:
        results["Text with Image"] = test_text_with_image(token, image_input)
    
    # Video tests (commented out by default as they take a long time)
    print("\n" + "="*60)
    print("VIDEO TESTS")
    print("="*60)
    print("⚠ Video tests are disabled by default (they take 5-10 minutes each)")
    print("  Uncomment the lines below to run video tests")
    
    # Uncomment to run video tests:
    # video_uri = test_video_text_to_video(token)
    # if video_uri:
    #     time.sleep(2)
    #     results["Video Extend"] = test_video_extend(token, video_uri)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*60)
    print(f"Results: {passed}/{total} tests passed")
    print("="*60)
    
    # Cleanup
    if os.path.exists(TEST_IMAGE_PATH):
        try:
            os.remove(TEST_IMAGE_PATH)
            print(f"\n✓ Cleaned up test image: {TEST_IMAGE_PATH}")
        except Exception:
            pass


if __name__ == "__main__":
    main()

