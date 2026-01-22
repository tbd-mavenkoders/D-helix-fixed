#!/usr/bin/env python3
"""
Test client for D-Helix FastAPI server
Tests both C and C++ binary verification

Usage:
    python test_client.py [--server URL]
"""

import requests
import argparse
import sys
import os
import tempfile
import subprocess

# Default server URL
DEFAULT_SERVER = "http://localhost:10012"


def create_test_c_binary():
    """Create a simple C test binary and source code."""
    c_source = """
int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    return a * b;
}

int main() {
    return add(1, 2) + multiply(3, 4);
}
"""
    
    decompiled_code = """int add(int a0, int a1) {
    return a0 + a1;
}
"""
    
    # Create temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = os.path.join(tmpdir, "test_c.c")
        binary_path = os.path.join(tmpdir, "test_c_binary")
        decompiled_path = os.path.join(tmpdir, "add_decompiled.c")
        
        # Write source
        with open(source_path, 'w') as f:
            f.write(c_source)
        
        # Compile
        result = subprocess.run(
            ["gcc", "-o", binary_path, source_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Failed to compile C test binary: {result.stderr}")
            return None, None
        
        # Write decompiled code
        with open(decompiled_path, 'w') as f:
            f.write(decompiled_code)
        
        # Read binary
        with open(binary_path, 'rb') as f:
            binary_data = f.read()
        
        return binary_data, decompiled_code


def create_test_cpp_binary():
    """Create a simple C++ test binary and source code."""
    cpp_source = """
extern "C" int global_add(int a, int b) {
    return a + b;
}

class Calculator {
public:
    int add(int a, int b) {
        return a + b;
    }
};

int main() {
    Calculator calc;
    return global_add(1, 2) + calc.add(3, 4);
}
"""
    
    decompiled_code = """int global_add(int a0, int a1) {
    return a0 + a1;
}
"""
    
    # Create temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = os.path.join(tmpdir, "test_cpp.cpp")
        binary_path = os.path.join(tmpdir, "test_cpp_binary")
        
        # Write source
        with open(source_path, 'w') as f:
            f.write(cpp_source)
        
        # Compile
        result = subprocess.run(
            ["g++", "-o", binary_path, source_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Failed to compile C++ test binary: {result.stderr}")
            return None, None
        
        # Read binary
        with open(binary_path, 'rb') as f:
            binary_data = f.read()
        
        return binary_data, decompiled_code


def test_health_check(server_url: str) -> bool:
    """Test the health check endpoint."""
    print("\n=== Testing Health Check ===")
    try:
        response = requests.get(f"{server_url}/health", timeout=5)
        if response.status_code == 200:
            print(f"✓ Health check passed: {response.json()}")
            return True
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Health check error: {e}")
        return False


def test_c_verification(server_url: str) -> bool:
    """Test C binary verification."""
    print("\n=== Testing C Binary Verification ===")
    
    # Create test binary and decompiled code
    binary_data, decompiled_code = create_test_c_binary()
    if binary_data is None:
        print("✗ Could not create C test binary")
        return False
    
    try:
        # Send verification request
        files = {
            'binary': ('test_c_binary', binary_data, 'application/octet-stream'),
            'decompiled_code': ('add.c', decompiled_code, 'text/plain')
        }
        data = {
            'function_name': 'add',
            'is_cpp': 'false'
        }
        
        print(f"Sending C verification request to {server_url}/verify...")
        response = requests.post(
            f"{server_url}/verify",
            files=files,
            data=data,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ C verification response received")
            print(f"  Request ID: {result.get('request_id')}")
            print(f"  Status: {result.get('status')}")
            print(f"  Result: {result.get('result')}")
            if result.get('error_message'):
                print(f"  Error: {result.get('error_message')}")
            return result.get('status') == 'success'
        else:
            print(f"✗ C verification failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ C verification error: {e}")
        return False


def test_cpp_verification(server_url: str) -> bool:
    """Test C++ binary verification."""
    print("\n=== Testing C++ Binary Verification ===")
    
    # Create test binary and decompiled code
    binary_data, decompiled_code = create_test_cpp_binary()
    if binary_data is None:
        print("✗ Could not create C++ test binary")
        return False
    
    try:
        # Send verification request
        files = {
            'binary': ('test_cpp_binary', binary_data, 'application/octet-stream'),
            'decompiled_code': ('global_add.cpp', decompiled_code, 'text/plain')
        }
        data = {
            'function_name': 'global_add',
            'is_cpp': 'true'
        }
        
        print(f"Sending C++ verification request to {server_url}/verify...")
        response = requests.post(
            f"{server_url}/verify",
            files=files,
            data=data,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ C++ verification response received")
            print(f"  Request ID: {result.get('request_id')}")
            print(f"  Status: {result.get('status')}")
            print(f"  Result: {result.get('result')}")
            if result.get('error_message'):
                print(f"  Error: {result.get('error_message')}")
            return result.get('status') == 'success'
        else:
            print(f"✗ C++ verification failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ C++ verification error: {e}")
        return False


def test_cpp_mangled_name(server_url: str) -> bool:
    """Test C++ binary verification with mangled function name."""
    print("\n=== Testing C++ Mangled Name Detection ===")
    
    # Use the same C++ binary
    binary_data, decompiled_code = create_test_cpp_binary()
    if binary_data is None:
        print("✗ Could not create C++ test binary")
        return False
    
    try:
        # Send verification request with mangled name (auto-detect C++)
        files = {
            'binary': ('test_cpp_binary', binary_data, 'application/octet-stream'),
            'decompiled_code': ('global_add.cpp', decompiled_code, 'text/plain')
        }
        data = {
            'function_name': '_Z10global_addii'  # Mangled C++ name
            # Note: is_cpp should be auto-detected from the mangled name
        }
        
        print(f"Sending request with mangled function name '_Z10global_addii'...")
        response = requests.post(
            f"{server_url}/verify",
            files=files,
            data=data,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Mangled name test response received")
            print(f"  Request ID: {result.get('request_id')}")
            print(f"  Status: {result.get('status')}")
            print(f"  Result: {result.get('result')}")
            if result.get('error_message'):
                print(f"  Error: {result.get('error_message')}")
            return result.get('status') == 'success'
        else:
            print(f"✗ Mangled name test failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Mangled name test error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test D-Helix FastAPI server")
    parser.add_argument(
        "--server", "-s",
        default=DEFAULT_SERVER,
        help=f"Server URL (default: {DEFAULT_SERVER})"
    )
    parser.add_argument(
        "--test", "-t",
        choices=["health", "c", "cpp", "mangled", "all"],
        default="all",
        help="Test to run (default: all)"
    )
    args = parser.parse_args()
    
    print(f"D-Helix API Test Client")
    print(f"Server: {args.server}")
    print("=" * 50)
    
    results = {}
    
    if args.test in ["health", "all"]:
        results["health"] = test_health_check(args.server)
    
    if args.test in ["c", "all"]:
        results["c"] = test_c_verification(args.server)
    
    if args.test in ["cpp", "all"]:
        results["cpp"] = test_cpp_verification(args.server)
    
    if args.test in ["mangled", "all"]:
        results["mangled"] = test_cpp_mangled_name(args.server)
    
    # Print summary
    print("\n" + "=" * 50)
    print("Test Summary:")
    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
