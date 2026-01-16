#!/usr/bin/env python3
"""
Test client for D-Helix Verification API
Creates fresh copies of binaries to avoid caching issues
"""

import requests
import json
import shutil
import os
import uuid
from pathlib import Path

# API endpoint
API_URL = "http://localhost:10012"

# Original binary location
ORIGINAL_BINARY = "/root/work/D-helix-fixed/D-helix/D_helix_angr/test_muqi/originalclang/test_simple_2"

# Temp directory for fresh binary copies
TEMP_DIR = "/tmp/api_test_binaries"


def get_fresh_binary():
    """Create a fresh copy of the binary with unique name to avoid caching"""
    os.makedirs(TEMP_DIR, exist_ok=True)
    unique_name = f"binary_{uuid.uuid4().hex[:8]}"
    fresh_path = os.path.join(TEMP_DIR, unique_name)
    shutil.copy2(ORIGINAL_BINARY, fresh_path)
    os.chmod(fresh_path, 0o755)
    print(f"   Created fresh binary: {fresh_path}")
    return fresh_path


def cleanup_temp_binaries():
    """Clean up temporary binary copies"""
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print("   Cleaned up temp binaries")


def test_verification():
    """Test the verification endpoint with test_simple binary - add function"""
    print("=" * 80)
    print("D-Helix API Client Test - add() function")
    print("=" * 80)
    
    # Check if API is healthy
    print("\n1. Checking API health...")
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ API is healthy")
        else:
            print("❌ API health check failed")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Is the server running?")
        return False
    
    # Check if original binary exists
    if not Path(ORIGINAL_BINARY).exists():
        print(f"\n❌ Binary not found: {ORIGINAL_BINARY}")
        print("Please ensure test binary exists")
        return False
    
    # Get fresh binary copy
    binary_path = get_fresh_binary()
    
    # Correct decompiled code for 'add' function
    decompiled_code = """
int add(int a, int b) {
    return a + b;
}
"""
    
    print("\n2. Sending verification request...")
    print(f"   Binary: {binary_path}")
    print(f"   Function: add")
    
    try:
        with open(binary_path, 'rb') as binary_file:
            files = {
                'binary': ('test_binary', binary_file, 'application/octet-stream'),
                'decompiled_code': ('add.c', decompiled_code, 'text/plain')
            }
            data = {
                'function_name': 'add'
            }
            
            response = requests.post(
                f"{API_URL}/verify",
                files=files,
                data=data,
                timeout=120
            )
        
        print(f"\n3. Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ Verification Complete!")
            print(f"   Request ID: {result['request_id']}")
            print(f"   Status: {result['status']}")
            print(f"   Result: {result['result']}")
            
            if result['result'] == 'unsat':
                print("\n   ✅ EXPECTED: Binary and decompiled code are semantically EQUIVALENT")
            elif result['result'] == 'sat':
                print("\n   ⚠️  UNEXPECTED: Decompilation may have a bug!")
            
            return True
        else:
            print(f"\n❌ Verification failed:")
            print(response.text)
            return False
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def test_subtract_function():
    """Test the subtract function"""
    print("\n" + "=" * 80)
    print("Testing 'subtract' function")
    print("=" * 80)
    
    binary_path = get_fresh_binary()
    
    decompiled_code = """
int subtract(int a, int b) {
    return a - b;
}
"""
    
    try:
        with open(binary_path, 'rb') as binary_file:
            files = {
                'binary': ('test_binary', binary_file, 'application/octet-stream'),
                'decompiled_code': ('subtract.c', decompiled_code, 'text/plain')
            }
            data = {
                'function_name': 'subtract'
            }
            
            response = requests.post(
                f"{API_URL}/verify",
                files=files,
                data=data,
                timeout=120
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Result: {result['result']}")
            
            if result['result'] == 'unsat':
                print("   ✅ subtract() function is correctly decompiled")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_buggy_decompilation():
    """Test with intentionally buggy decompilation"""
    print("\n" + "=" * 80)
    print("Testing BUGGY decompilation (should return 'sat')")
    print("=" * 80)
    
    binary_path = get_fresh_binary()
    
    # Intentionally wrong: returns a * b instead of a + b
    buggy_decompiled_code = """
int add(int a, int b) {
    return a * b;  // BUG: should be a + b
}
"""
    
    print("   Expected: Result should be 'sat' (bug detected)")
    
    try:
        with open(binary_path, 'rb') as binary_file:
            files = {
                'binary': ('test_binary', binary_file, 'application/octet-stream'),
                'decompiled_code': ('add_buggy.c', buggy_decompiled_code, 'text/plain')
            }
            data = {
                'function_name': 'add'
            }
            
            response = requests.post(
                f"{API_URL}/verify",
                files=files,
                data=data,
                timeout=120
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n   Result: {result['result']}")
            
            if result['result'] == 'sat':
                print("   ✅ BUG DETECTED! (as expected)")
                if result.get('counterexample'):
                    print("   Counterexample inputs:")
                    print(json.dumps(result['counterexample'], indent=4))
            else:
                print("   ⚠️  Unexpected: Bug was not detected")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    try:
        # Clean up any previous temp files
        cleanup_temp_binaries()
        
        # Test 1: Correct decompilation
        test1_ok = test_verification()
        
        # Test 2: Another correct function
        test2_ok = test_subtract_function()
        
        # Test 3: Buggy decompilation (should detect difference)
        test3_ok = test_buggy_decompilation()
        
        # Final cleanup
        cleanup_temp_binaries()
        
        print("\n" + "=" * 80)
        print("All tests complete!")
        print(f"  Test 1 (add): {'✅' if test1_ok else '❌'}")
        print(f"  Test 2 (subtract): {'✅' if test2_ok else '❌'}")
        print(f"  Test 3 (buggy): {'✅' if test3_ok else '❌'}")
        print("=" * 80)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to API server")
        print("   Please start the server first:")
        print("   cd /root/work/D-helix-fixed/fastapi_server")
        print("   source /root/.virtualenvs/angr/bin/activate")
        print("   python api_server.py")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
    finally:
        # Always cleanup
        cleanup_temp_binaries()
