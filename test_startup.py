#!/usr/bin/env python3
"""
Test script to verify startup logs and configuration.
Run this to test if the application can start successfully.
"""
import sys
import os

# Set minimal required environment variables for testing
if not os.getenv("SECRET_KEY"):
    print("⚠️  WARNING: SECRET_KEY not set, using test value")
    os.environ["SECRET_KEY"] = "test-secret-key-for-startup-verification"

if not os.getenv("GEMINI_API_KEY"):
    print("⚠️  WARNING: GEMINI_API_KEY not set, using test value")
    os.environ["GEMINI_API_KEY"] = "test-gemini-key-for-startup-verification"

print("\n" + "=" * 80)
print("TESTING APPLICATION STARTUP")
print("=" * 80)
print("\nThis script will test if the application can start successfully.")
print("Watch for any ❌ (error) symbols in the logs below.\n")
print("=" * 80)

try:
    # Import app (this will trigger all initialization code)
    print("\n🔄 Importing application modules...")
    from app import app
    
    print("\n" + "=" * 80)
    print("✓ APPLICATION IMPORT SUCCESSFUL")
    print("=" * 80)
    print("\nThe application initialized without errors!")
    print("You can now deploy this to production.\n")
    print("Key things to check in production logs:")
    print("  1. Configuration validation passes (✓)")
    print("  2. All directories are created and writable")
    print("  3. Database loads successfully")
    print("  4. All routers register successfully")
    print("  5. Application startup completes")
    print("\n" + "=" * 80)
    
    sys.exit(0)
    
except Exception as e:
    print("\n" + "=" * 80)
    print("❌ APPLICATION STARTUP FAILED")
    print("=" * 80)
    print(f"\nError: {e}\n")
    import traceback
    traceback.print_exc()
    print("\n" + "=" * 80)
    print("Please fix the errors above before deploying to production.")
    print("=" * 80)
    sys.exit(1)

