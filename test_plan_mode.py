"""Test script for plan mode functionality."""
import requests
import json
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
API_ENDPOINT = f"{BASE_URL}/api/generate-unified"

# Test credentials (update with actual test user)
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword"


def login(email: str, password: str) -> str:
    """Login and get access token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password}
    )
    
    if response.status_code == 200:
        data = response.json()
        return data["access_token"]
    else:
        print(f"Login failed: {response.status_code} - {response.text}")
        return None


def create_plan_from_script(token: str, script: str) -> Dict[str, Any]:
    """Create a plan from a narrative script."""
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "mode": "plan",
        "prompt": script,  # Required field, using script as prompt
        "script": script
    }
    
    print("\n" + "="*60)
    print("CREATING PLAN FROM SCRIPT")
    print("="*60)
    print(f"Script: {script[:200]}...")
    print()
    
    response = requests.post(API_ENDPOINT, headers=headers, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Plan created successfully!")
        print(f"Conversation ID: {data['conversation_id']}")
        print(f"Plan created: {data.get('plan_created', False)}")
        
        if data.get('execution_plan'):
            plan = data['execution_plan']
            print(f"\nPlan Details:")
            print(f"  - Scenes: {len(plan['scenes'])}")
            print(f"  - Overall strategy: {plan['overall_strategy']}")
            print(f"  - Estimated duration: {plan.get('estimated_duration', 'N/A')}")
            
            if data.get('estimated_cost'):
                cost = data['estimated_cost']
                print(f"  - Estimated cost: ${cost['total_cost']:.2f}")
            
            print(f"\nScene Breakdown:")
            for i, scene in enumerate(plan['scenes'], 1):
                print(f"\n  Scene {i} ({scene['id']}):")
                print(f"    - Mode: {scene['mode']}")
                print(f"    - Prompt: {scene['prompt'][:80]}...")
                print(f"    - Duration: {scene['duration_hint']}")
                print(f"    - Pre-generate images: {scene['pre_generate_images']}")
                print(f"    - Dependencies: {scene['dependencies']}")
                print(f"    - Reasoning: {scene['reasoning'][:100]}...")
        
        return data
    else:
        print(f"❌ Plan creation failed: {response.status_code}")
        print(f"Error: {response.text}")
        return None


def execute_plan(token: str, plan: Dict[str, Any], conversation_id: str = None) -> Dict[str, Any]:
    """Execute a video generation plan."""
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "mode": "plan",
        "prompt": "Execute plan",  # Required field
        "execution_plan": plan
    }
    
    if conversation_id:
        payload["conversation_id"] = conversation_id
    
    print("\n" + "="*60)
    print("EXECUTING PLAN")
    print("="*60)
    print(f"Executing {len(plan['scenes'])} scenes...")
    print()
    
    response = requests.post(API_ENDPOINT, headers=headers, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Plan executed successfully!")
        print(f"Conversation ID: {data['conversation_id']}")
        print(f"Plan executed: {data.get('plan_executed', False)}")
        
        if data.get('scene_results'):
            results = data['scene_results']
            success_count = sum(1 for r in results if r['success'])
            print(f"\nExecution Results:")
            print(f"  - Total scenes: {len(results)}")
            print(f"  - Successful: {success_count}")
            print(f"  - Failed: {len(results) - success_count}")
            
            if data.get('cost'):
                cost = data['cost']
                print(f"  - Total cost: ${cost['total_cost']:.2f}")
            
            print(f"\nScene Results:")
            for result in results:
                status = "✅" if result['success'] else "❌"
                print(f"\n  {status} {result['scene_id']}:")
                print(f"    - Success: {result['success']}")
                if result['success']:
                    print(f"    - Video URL: {result['video_url']}")
                    print(f"    - Duration: {result.get('duration_seconds', 0):.1f}s")
                else:
                    print(f"    - Error: {result.get('error', 'Unknown error')}")
        
        if data.get('assets'):
            print(f"\n📹 Generated {len(data['assets'])} video assets")
            for asset in data['assets']:
                print(f"  - {asset['scene_id']}: {asset['url']}")
        
        return data
    else:
        print(f"❌ Plan execution failed: {response.status_code}")
        print(f"Error: {response.text}")
        return None


def test_simple_parallel_scenes():
    """Test: Simple 2-3 scene narrative with parallel generation."""
    script = """
    Scene 1: A serene sunrise over mountains, golden light illuminating snow-capped peaks.
    Scene 2: A tranquil beach at sunset, waves gently lapping at the shore.
    Scene 3: A starry night sky with the Milky Way visible above a desert landscape.
    """
    
    print("\n" + "#"*60)
    print("TEST 1: SIMPLE PARALLEL SCENES")
    print("#"*60)
    
    token = login(TEST_EMAIL, TEST_PASSWORD)
    if not token:
        print("❌ Login failed, skipping test")
        return
    
    # Create plan
    result = create_plan_from_script(token, script)
    if not result:
        return
    
    # Wait before execution (optional)
    print("\n⏳ Waiting 3 seconds before execution...")
    time.sleep(3)
    
    # Execute plan
    plan = result['execution_plan']
    conv_id = result['conversation_id']
    execute_plan(token, plan, conv_id)


def test_sequential_action_sequence():
    """Test: Action sequence with sequential execution and extend_video."""
    script = """
    A superhero origin story:
    
    Act 1: An ordinary person discovers glowing ancient artifact in a cave.
    Act 2: The artifact begins to glow brighter, energy swirling around the person.
    Act 3: The energy transforms the person, giving them glowing powers and a heroic costume.
    Act 4: The newly transformed hero flies up through the cave opening into the sky.
    """
    
    print("\n" + "#"*60)
    print("TEST 2: SEQUENTIAL ACTION SEQUENCE")
    print("#"*60)
    
    token = login(TEST_EMAIL, TEST_PASSWORD)
    if not token:
        print("❌ Login failed, skipping test")
        return
    
    # Create plan
    result = create_plan_from_script(token, script)
    if not result:
        return
    
    # Optionally modify plan before execution
    # (user could edit the plan here)
    
    # Wait before execution (optional)
    print("\n⏳ Waiting 3 seconds before execution...")
    time.sleep(3)
    
    # Execute plan
    plan = result['execution_plan']
    conv_id = result['conversation_id']
    execute_plan(token, plan, conv_id)


def test_character_story_with_images():
    """Test: Character-based story with image pre-generation."""
    script = """
    A wizard's journey:
    
    Scene 1: An elderly wizard with a long white beard and blue robes stands in his tower library surrounded by ancient books.
    Scene 2: The same wizard casts a spell, magical runes glowing in the air around him.
    Scene 3: The wizard teleports to a mystical forest, appearing in a flash of blue light.
    Scene 4: The wizard encounters a dragon in the forest clearing, staff raised defensively.
    """
    
    print("\n" + "#"*60)
    print("TEST 3: CHARACTER STORY WITH IMAGE PRE-GENERATION")
    print("#"*60)
    
    token = login(TEST_EMAIL, TEST_PASSWORD)
    if not token:
        print("❌ Login failed, skipping test")
        return
    
    # Create plan
    result = create_plan_from_script(token, script)
    if not result:
        return
    
    # Wait before execution
    print("\n⏳ Waiting 3 seconds before execution...")
    time.sleep(3)
    
    # Execute plan
    plan = result['execution_plan']
    conv_id = result['conversation_id']
    execute_plan(token, plan, conv_id)


def test_plan_editing():
    """Test: Create plan, edit it, then execute."""
    script = """
    A time-lapse journey:
    Scene 1: A seed planted in soil.
    Scene 2: A sprout emerging from the ground.
    Scene 3: A sapling growing taller.
    Scene 4: A full-grown tree with leaves swaying.
    """
    
    print("\n" + "#"*60)
    print("TEST 4: PLAN EDITING")
    print("#"*60)
    
    token = login(TEST_EMAIL, TEST_PASSWORD)
    if not token:
        print("❌ Login failed, skipping test")
        return
    
    # Create plan
    result = create_plan_from_script(token, script)
    if not result:
        return
    
    plan = result['execution_plan']
    
    # Edit the plan (simulate user editing)
    print("\n✏️  Editing plan...")
    print("  - Changing scene 2 to use frames_to_video mode")
    print("  - Updating scene 3 prompt for more detail")
    
    if len(plan['scenes']) >= 2:
        plan['scenes'][1]['mode'] = 'frames_to_video'
        plan['scenes'][1]['reasoning'] = 'Modified to use frames for precise transition'
    
    if len(plan['scenes']) >= 3:
        plan['scenes'][2]['prompt'] = plan['scenes'][2]['prompt'] + " with morning sunlight filtering through leaves"
    
    # Wait before execution
    print("\n⏳ Waiting 3 seconds before execution...")
    time.sleep(3)
    
    # Execute edited plan
    conv_id = result['conversation_id']
    execute_plan(token, plan, conv_id)


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("PLAN MODE TEST SUITE")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print(f"Test user: {TEST_EMAIL}")
    print()
    
    # Run tests
    try:
        # Test 1: Simple parallel scenes
        test_simple_parallel_scenes()
        
        print("\n\n" + "⏳"*20)
        print("Waiting 10 seconds between tests...")
        time.sleep(10)
        
        # Test 2: Sequential action sequence
        test_sequential_action_sequence()
        
        print("\n\n" + "⏳"*20)
        print("Waiting 10 seconds between tests...")
        time.sleep(10)
        
        # Test 3: Character story with images
        test_character_story_with_images()
        
        print("\n\n" + "⏳"*20)
        print("Waiting 10 seconds between tests...")
        time.sleep(10)
        
        # Test 4: Plan editing
        test_plan_editing()
        
    except KeyboardInterrupt:
        print("\n\n❌ Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("TEST SUITE COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()

