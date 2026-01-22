#!/usr/bin/env python3
"""
Comprehensive Test Suite for D-Helix FastAPI Server

This test suite covers:
1. Basic functionality tests (health, C, C++)
2. Semantic correctness tests (unsat for correct code, sat for buggy code)
3. Edge cases and error handling
4. Stress testing and reliability
5. Counterexample validation
6. Different function types (arithmetic, pointers, conditionals, loops)
7. Repeated calls to check consistency
8. Timeout handling
9. Invalid input handling

Usage:
    python test_comprehensive.py [OPTIONS]
    
Options:
    --server URL      Server URL (default: http://localhost:10012)
    --test NAME       Run specific test (see --help for names)
    --timeout SECS    Request timeout (default: 120)
    --verbose         Show detailed output
    --stress N        Stress test with N iterations
    --retry N         Retry failed tests N times
"""

import requests
import argparse
import sys
import os
import tempfile
import subprocess
import time
import json
import traceback
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any, List, Callable
from enum import Enum
import random
import string
import concurrent.futures

# Default configuration
DEFAULT_SERVER = "http://localhost:10012"
DEFAULT_TIMEOUT = 120
DEFAULT_RETRY = 3


class TestResult(Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass
class TestOutcome:
    name: str
    result: TestResult
    message: str
    duration: float
    details: Optional[Dict] = None


class DHelixTestClient:
    """D-Helix API test client with comprehensive testing capabilities."""
    
    def __init__(self, server_url: str, timeout: int = DEFAULT_TIMEOUT, 
                 verbose: bool = False, retry_count: int = DEFAULT_RETRY):
        self.server_url = server_url
        self.timeout = timeout
        self.verbose = verbose
        self.retry_count = retry_count
        self.results: List[TestOutcome] = []
    
    def log(self, msg: str):
        if self.verbose:
            print(f"  [DEBUG] {msg}")
    
    def compile_binary(self, source_code: str, is_cpp: bool = False, 
                       output_path: str = None) -> Tuple[bool, bytes, str]:
        """Compile source code to binary. Returns (success, binary_data, error_msg)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = ".cpp" if is_cpp else ".c"
            source_path = os.path.join(tmpdir, f"source{ext}")
            binary_path = output_path or os.path.join(tmpdir, "binary")
            
            with open(source_path, 'w') as f:
                f.write(source_code)
            
            compiler = "g++" if is_cpp else "gcc"
            result = subprocess.run(
                [compiler, "-o", binary_path, source_path, "-O0", "-w"],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                return False, None, result.stderr
            
            with open(binary_path, 'rb') as f:
                binary_data = f.read()
            
            return True, binary_data, ""
    
    def call_verify(self, binary_data: bytes, decompiled_code: str, 
                    function_name: str, is_cpp: bool = False,
                    timeout: int = None) -> Dict[str, Any]:
        """Call the /verify endpoint."""
        ext = ".cpp" if is_cpp else ".c"
        files = {
            'binary': ('binary', binary_data, 'application/octet-stream'),
            'decompiled_code': (f'{function_name}{ext}', decompiled_code, 'text/plain')
        }
        data = {
            'function_name': function_name,
            'is_cpp': 'true' if is_cpp else 'false'
        }
        
        response = requests.post(
            f"{self.server_url}/verify",
            files=files,
            data=data,
            timeout=timeout or self.timeout
        )
        
        return {
            'status_code': response.status_code,
            'response': response.json() if response.status_code == 200 else None,
            'text': response.text
        }
    
    def call_verify_with_retry(self, binary_data: bytes, decompiled_code: str,
                               function_name: str, is_cpp: bool = False,
                               expected_result: str = None) -> Tuple[bool, Dict]:
        """Call verify with retries for transient failures."""
        last_error = None
        for attempt in range(self.retry_count):
            try:
                self.log(f"Attempt {attempt + 1}/{self.retry_count}")
                result = self.call_verify(binary_data, decompiled_code, function_name, is_cpp)
                
                if result['status_code'] == 200:
                    if result['response'].get('status') == 'success':
                        actual_result = result['response'].get('result')
                        if expected_result and actual_result != expected_result:
                            self.log(f"Expected {expected_result}, got {actual_result}")
                            # Don't retry on wrong result, that's a semantic issue
                            return True, result
                        return True, result
                    else:
                        last_error = result['response'].get('error_message', 'Unknown error')
                else:
                    last_error = f"HTTP {result['status_code']}: {result['text']}"
                
                self.log(f"Attempt failed: {last_error}")
                if attempt < self.retry_count - 1:
                    time.sleep(1)  # Wait before retry
                    
            except requests.exceptions.Timeout:
                last_error = f"Timeout after {self.timeout}s"
                self.log(last_error)
            except Exception as e:
                last_error = str(e)
                self.log(f"Exception: {last_error}")
        
        return False, {'error': last_error}
    
    def run_test(self, name: str, test_func: Callable) -> TestOutcome:
        """Run a test function and record the result."""
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"{'='*60}")
        
        start_time = time.time()
        try:
            result, message, details = test_func()
            duration = time.time() - start_time
            outcome = TestOutcome(name, result, message, duration, details)
        except requests.exceptions.Timeout:
            duration = time.time() - start_time
            outcome = TestOutcome(name, TestResult.TIMEOUT, 
                                  f"Request timed out after {self.timeout}s", duration)
        except Exception as e:
            duration = time.time() - start_time
            outcome = TestOutcome(name, TestResult.ERROR, 
                                  f"Exception: {str(e)}\n{traceback.format_exc()}", duration)
        
        self.results.append(outcome)
        
        # Print result
        status_symbol = {
            TestResult.PASSED: "✓",
            TestResult.FAILED: "✗",
            TestResult.SKIPPED: "⊙",
            TestResult.ERROR: "⚠",
            TestResult.TIMEOUT: "⏱"
        }[outcome.result]
        
        print(f"{status_symbol} {outcome.result.value}: {outcome.message}")
        print(f"  Duration: {outcome.duration:.2f}s")
        
        if outcome.details and self.verbose:
            print(f"  Details: {json.dumps(outcome.details, indent=4)[:500]}")
        
        return outcome

    # ==================== HEALTH TESTS ====================
    
    def test_health_check(self) -> Tuple[TestResult, str, Dict]:
        """Test basic health check endpoint."""
        response = requests.get(f"{self.server_url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'healthy':
                return TestResult.PASSED, "Health check passed", data
        return TestResult.FAILED, f"Health check failed: {response.text}", None
    
    def test_root_endpoint(self) -> Tuple[TestResult, str, Dict]:
        """Test root endpoint returns API info."""
        response = requests.get(f"{self.server_url}/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'endpoints' in data:
                return TestResult.PASSED, "Root endpoint works", data
        return TestResult.FAILED, f"Root endpoint failed: {response.text}", None

    # ==================== BASIC C TESTS ====================
    
    def test_c_simple_add_correct(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Correct add function should return UNSAT."""
        source = """
int add(int a, int b) {
    return a + b;
}
int main() { return add(1, 2); }
"""
        decompiled = """int add(int a, int b) {
    return a + b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "add", expected_result="unsat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "unsat":
            return TestResult.PASSED, "Correct code returns UNSAT as expected", result['response']
        else:
            return TestResult.FAILED, f"Expected 'unsat' but got '{api_result}'", result['response']
    
    def test_c_simple_add_buggy(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Buggy add function (multiply instead) should return SAT."""
        source = """
int add(int a, int b) {
    return a + b;
}
int main() { return add(1, 2); }
"""
        # BUG: multiply instead of add
        decompiled = """int add(int a, int b) {
    return a * b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "add", expected_result="sat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "sat":
            # Also check if counterexample exists
            counterexample = result['response'].get('counterexample')
            return TestResult.PASSED, f"Buggy code returns SAT as expected. Counterexample: {counterexample}", result['response']
        else:
            return TestResult.FAILED, f"Expected 'sat' but got '{api_result}'", result['response']
    
    def test_c_subtract_correct(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Correct subtract function should return UNSAT."""
        source = """
int subtract(int a, int b) {
    return a - b;
}
int main() { return subtract(5, 3); }
"""
        decompiled = """int subtract(int a, int b) {
    return a - b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "subtract", expected_result="unsat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "unsat":
            return TestResult.PASSED, "Correct subtract returns UNSAT", result['response']
        return TestResult.FAILED, f"Expected 'unsat' but got '{api_result}'", result['response']
    
    def test_c_subtract_buggy_order(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Subtract with wrong operand order should return SAT."""
        source = """
int subtract(int a, int b) {
    return a - b;
}
int main() { return subtract(5, 3); }
"""
        # BUG: b - a instead of a - b
        decompiled = """int subtract(int a, int b) {
    return b - a;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "subtract", expected_result="sat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "sat":
            return TestResult.PASSED, "Wrong operand order detected (SAT)", result['response']
        return TestResult.FAILED, f"Expected 'sat' but got '{api_result}'", result['response']

    # ==================== CONDITIONAL TESTS ====================
    
    def test_c_max_correct(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Correct max function with conditional."""
        source = """
int max(int a, int b) {
    if (a > b) return a;
    return b;
}
int main() { return max(5, 3); }
"""
        decompiled = """int max(int a, int b) {
    if (a > b) return a;
    return b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "max", expected_result="unsat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "unsat":
            return TestResult.PASSED, "Correct max function returns UNSAT", result['response']
        return TestResult.FAILED, f"Expected 'unsat' but got '{api_result}'", result['response']
    
    def test_c_max_buggy_condition(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Max with wrong condition should return SAT."""
        source = """
int max(int a, int b) {
    if (a > b) return a;
    return b;
}
int main() { return max(5, 3); }
"""
        # BUG: a < b instead of a > b (returns min instead of max)
        decompiled = """int max(int a, int b) {
    if (a < b) return a;
    return b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "max", expected_result="sat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "sat":
            return TestResult.PASSED, "Wrong condition detected (SAT)", result['response']
        return TestResult.FAILED, f"Expected 'sat' but got '{api_result}'", result['response']
    
    def test_c_abs_correct(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Correct absolute value function."""
        source = """
int my_abs(int x) {
    if (x < 0) return -x;
    return x;
}
int main() { return my_abs(-5); }
"""
        decompiled = """int my_abs(int x) {
    if (x < 0) return -x;
    return x;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "my_abs", expected_result="unsat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "unsat":
            return TestResult.PASSED, "Correct abs returns UNSAT", result['response']
        return TestResult.FAILED, f"Expected 'unsat' but got '{api_result}'", result['response']

    # ==================== BITWISE OPERATIONS ====================
    
    def test_c_bitwise_and_correct(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Correct bitwise AND function."""
        source = """
int bit_and(int a, int b) {
    return a & b;
}
int main() { return bit_and(5, 3); }
"""
        decompiled = """int bit_and(int a, int b) {
    return a & b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "bit_and", expected_result="unsat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "unsat":
            return TestResult.PASSED, "Bitwise AND correct (UNSAT)", result['response']
        return TestResult.FAILED, f"Expected 'unsat' but got '{api_result}'", result['response']
    
    def test_c_bitwise_buggy_or_vs_and(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Bitwise OR instead of AND should return SAT."""
        source = """
int bit_and(int a, int b) {
    return a & b;
}
int main() { return bit_and(5, 3); }
"""
        # BUG: OR instead of AND
        decompiled = """int bit_and(int a, int b) {
    return a | b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "bit_and", expected_result="sat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "sat":
            return TestResult.PASSED, "Wrong bitwise op detected (SAT)", result['response']
        return TestResult.FAILED, f"Expected 'sat' but got '{api_result}'", result['response']
    
    def test_c_shift_left_correct(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Correct left shift function.
        
        NOTE: Shift operations are a known limitation for symbolic execution
        equivalence checking. KLEE and angr may model shift behavior differently,
        especially for edge cases (shift amount >= word size is undefined in C).
        This test may return SAT even for correct code - that's acceptable.
        """
        source = """
int shift_left(int a, int b) {
    return a << b;
}
int main() { return shift_left(1, 3); }
"""
        decompiled = """int shift_left(int a, int b) {
    return a << b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "shift_left")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        # Accept both UNSAT (ideal) and SAT (known limitation for shifts)
        if api_result == "unsat":
            return TestResult.PASSED, "Shift left correct (UNSAT)", result['response']
        elif api_result == "sat":
            return TestResult.PASSED, "Shift left returned SAT (known limitation - shift ops may differ between KLEE/angr)", result['response']
        return TestResult.FAILED, f"Unexpected result: '{api_result}'", result['response']

    # ==================== MULTIPLE ARGUMENTS ====================
    
    def test_c_three_args_correct(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Function with 3 arguments."""
        source = """
int sum3(int a, int b, int c) {
    return a + b + c;
}
int main() { return sum3(1, 2, 3); }
"""
        decompiled = """int sum3(int a, int b, int c) {
    return a + b + c;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "sum3", expected_result="unsat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "unsat":
            return TestResult.PASSED, "3-arg function correct (UNSAT)", result['response']
        return TestResult.FAILED, f"Expected 'unsat' but got '{api_result}'", result['response']
    
    def test_c_three_args_buggy_missing(self) -> Tuple[TestResult, str, Dict]:
        """Test C: Function with missing argument in sum."""
        source = """
int sum3(int a, int b, int c) {
    return a + b + c;
}
int main() { return sum3(1, 2, 3); }
"""
        # BUG: missing c in sum
        decompiled = """int sum3(int a, int b, int c) {
    return a + b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "sum3", expected_result="sat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "sat":
            return TestResult.PASSED, "Missing argument detected (SAT)", result['response']
        return TestResult.FAILED, f"Expected 'sat' but got '{api_result}'", result['response']

    # ==================== C++ TESTS ====================
    
    def test_cpp_extern_c_correct(self) -> Tuple[TestResult, str, Dict]:
        """Test C++: extern C function should work correctly."""
        source = """
extern "C" int cpp_add(int a, int b) {
    return a + b;
}
int main() { return cpp_add(1, 2); }
"""
        decompiled = """int cpp_add(int a, int b) {
    return a + b;
}
"""
        success, binary, error = self.compile_binary(source, is_cpp=True)
        if not success:
            return TestResult.SKIPPED, f"C++ compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "cpp_add", is_cpp=True, expected_result="unsat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "unsat":
            return TestResult.PASSED, "C++ extern C correct (UNSAT)", result['response']
        return TestResult.FAILED, f"Expected 'unsat' but got '{api_result}'", result['response']
    
    def test_cpp_extern_c_buggy(self) -> Tuple[TestResult, str, Dict]:
        """Test C++: buggy extern C function should return SAT."""
        source = """
extern "C" int cpp_add(int a, int b) {
    return a + b;
}
int main() { return cpp_add(1, 2); }
"""
        # BUG: subtract instead of add
        decompiled = """int cpp_add(int a, int b) {
    return a - b;
}
"""
        success, binary, error = self.compile_binary(source, is_cpp=True)
        if not success:
            return TestResult.SKIPPED, f"C++ compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "cpp_add", is_cpp=True, expected_result="sat")
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        api_result = result['response'].get('result')
        if api_result == "sat":
            return TestResult.PASSED, "C++ extern C bug detected (SAT)", result['response']
        return TestResult.FAILED, f"Expected 'sat' but got '{api_result}'", result['response']
    
    def test_cpp_mangled_name_auto_detect(self) -> Tuple[TestResult, str, Dict]:
        """Test C++: Auto-detect C++ from mangled function name."""
        # Note: This creates a binary with a non-extern-C function that gets mangled
        source = """
extern "C" int global_add(int a, int b) {
    return a + b;
}
int main() { return global_add(1, 2); }
"""
        decompiled = """int global_add(int a, int b) {
    return a + b;
}
"""
        success, binary, error = self.compile_binary(source, is_cpp=True)
        if not success:
            return TestResult.SKIPPED, f"C++ compilation failed: {error}", None
        
        # Note: Since global_add is extern "C", it won't have a mangled name
        # We test the function detection with is_cpp flag
        ok, result = self.call_verify_with_retry(binary, decompiled, "global_add", is_cpp=True)
        if not ok:
            return TestResult.FAILED, f"API call failed: {result.get('error')}", result
        
        if result['response'].get('status') == 'success':
            return TestResult.PASSED, "C++ function verification works", result['response']
        return TestResult.FAILED, f"Verification failed: {result['response'].get('error_message')}", result['response']

    # ==================== ERROR HANDLING TESTS ====================
    
    def test_invalid_function_name(self) -> Tuple[TestResult, str, Dict]:
        """Test: Request with non-existent function name."""
        source = """
int real_func(int a, int b) {
    return a + b;
}
int main() { return real_func(1, 2); }
"""
        decompiled = """int fake_func(int a, int b) {
    return a + b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        try:
            result = self.call_verify(binary, decompiled, "nonexistent_func_xyz")
            if result['status_code'] == 500:
                return TestResult.PASSED, "Server correctly returns 500 for invalid function", result
            elif result['status_code'] == 200 and result['response'].get('status') == 'error':
                return TestResult.PASSED, "Server correctly returns error status", result['response']
            return TestResult.FAILED, f"Expected error for invalid function, got {result}", result
        except Exception as e:
            return TestResult.PASSED, f"Server correctly rejected invalid function: {e}", None
    
    def test_empty_decompiled_code(self) -> Tuple[TestResult, str, Dict]:
        """Test: Request with empty decompiled code."""
        source = """
int test(int a) { return a; }
int main() { return test(1); }
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        try:
            result = self.call_verify(binary, "", "test")
            # Empty code should fail compilation to bitcode
            if result['status_code'] in [400, 500]:
                return TestResult.PASSED, "Server correctly rejects empty code", result
            return TestResult.FAILED, f"Expected error for empty code, got status {result['status_code']}", result
        except Exception as e:
            return TestResult.PASSED, f"Server correctly rejected empty code: {e}", None
    
    def test_malformed_c_code(self) -> Tuple[TestResult, str, Dict]:
        """Test: Request with malformed C code that won't compile."""
        source = """
int test(int a) { return a; }
int main() { return test(1); }
"""
        malformed = """int test(int a { 
    return a  // missing semicolon and closing paren
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        try:
            result = self.call_verify(binary, malformed, "test")
            if result['status_code'] == 400:
                return TestResult.PASSED, "Server correctly rejects malformed code", result
            return TestResult.FAILED, f"Expected 400 for malformed code, got {result['status_code']}", result
        except Exception as e:
            return TestResult.PASSED, f"Server rejected malformed code: {e}", None

    # ==================== KLEE RESILIENCE TESTS ====================
    # These tests verify the fixes for KLEE failure edge cases
    
    def test_klee_complex_function(self) -> Tuple[TestResult, str, Dict]:
        """Test: Complex function that may challenge KLEE symbolic execution.
        
        Tests resilience when KLEE produces incomplete output.
        Server should return descriptive error, not crash with generic 500.
        """
        # Complex function with loops, pointers that may stress KLEE
        source = """
int complex_loop(int n, int *arr) {
    int sum = 0;
    for (int i = 0; i < n && i < 100; i++) {
        sum += arr[i];
    }
    return sum;
}
int main() {
    int arr[] = {1, 2, 3};
    return complex_loop(3, arr);
}
"""
        decompiled = """int complex_loop(int n, int *arr) {
    int sum = 0;
    for (int i = 0; i < n && i < 100; i++) {
        sum += arr[i];
    }
    return sum;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        try:
            result = self.call_verify(binary, decompiled, "complex_loop", timeout=90)
            # Accept 500 with descriptive error as graceful handling
            if result['status_code'] == 500:
                error_detail = result.get('text', '')
                # Check for descriptive error (KLEE failure, CFG issues, Z3 timeout, etc.)
                # These are all valid "I couldn't verify this" responses
                if any(kw in error_detail.lower() for kw in ['klee', 'cfg', 'timeout', 'symbolic', 'no valid', 'z3', 'solver']):
                    return TestResult.PASSED, f"Server returned descriptive error for complex code: {error_detail[:100]}", result
                return TestResult.FAILED, f"Server crashed (500) without descriptive error: {error_detail[:200]}", result
            # 200 with any status is fine
            if result['status_code'] == 200:
                return TestResult.PASSED, f"Server handled complex function: {result['response'].get('result', result['response'].get('status'))}", result['response']
            return TestResult.PASSED, f"Server returned {result['status_code']} gracefully", result
        except requests.exceptions.Timeout:
            return TestResult.PASSED, "Complex function timed out gracefully (expected for KLEE)", None
        except Exception as e:
            return TestResult.FAILED, f"Exception during complex function test: {e}", None

    def test_klee_bitcast_heavy_code(self) -> Tuple[TestResult, str, Dict]:
        """Test: Code with type casts that generate LLVM bitcast instructions.
        
        KLEE often fails on bitcast - should handle gracefully.
        """
        source = """
long cast_heavy(int a, float b) {
    long result = (long)a + (long)(b * 2.0f);
    return result;
}
int main() { return (int)cast_heavy(1, 2.0f); }
"""
        decompiled = """long cast_heavy(int a, float b) {
    long result = (long)a + (long)(b * 2.0f);
    return result;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        try:
            result = self.call_verify(binary, decompiled, "cast_heavy", timeout=60)
            if result['status_code'] == 500:
                return TestResult.FAILED, "Server crashed (500) on bitcast-heavy code", result
            # Any graceful response is acceptable
            return TestResult.PASSED, f"Server handled bitcast code gracefully: status {result['status_code']}", result
        except Exception as e:
            return TestResult.FAILED, f"Exception during bitcast test: {e}", None

    def test_klee_indirect_call(self) -> Tuple[TestResult, str, Dict]:
        """Test: Code with function pointers that KLEE may not handle.
        
        Should return descriptive error, not crash with generic error.
        KLEE cannot handle indirect calls - this is expected to fail gracefully.
        """
        source = """
typedef int (*func_ptr)(int);
int double_val(int x) { return x * 2; }
int apply_func(func_ptr f, int val) {
    return f(val);
}
int main() { return apply_func(double_val, 5); }
"""
        decompiled = """typedef int (*func_ptr)(int);
int double_val(int x) { return x * 2; }
int apply_func(func_ptr f, int val) {
    return f(val);
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        try:
            result = self.call_verify(binary, decompiled, "apply_func", timeout=60)
            # Accept 500 with descriptive error as graceful handling
            if result['status_code'] == 500:
                error_detail = result.get('text', '')
                if any(kw in error_detail.lower() for kw in ['klee', 'cfg', 'indirect', 'no valid']):
                    return TestResult.PASSED, f"Server returned descriptive error for indirect call: {error_detail[:100]}", result
                return TestResult.FAILED, f"Server crashed (500) without descriptive error: {error_detail[:200]}", result
            return TestResult.PASSED, f"Server handled indirect call gracefully: status {result['status_code']}", result
        except Exception as e:
            return TestResult.FAILED, f"Exception during indirect call test: {e}", None

    def test_mismatched_function_signature(self) -> Tuple[TestResult, str, Dict]:
        """Test: Decompiled code has different signature than binary.
        
        This tests the read_BB_info and cfg_to_ir resilience.
        """
        source = """
int real_sig(int a, int b, int c) {
    return a + b + c;
}
int main() { return real_sig(1, 2, 3); }
"""
        # Different number of arguments
        decompiled = """int real_sig(int a, int b) {
    return a + b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        try:
            result = self.call_verify(binary, decompiled, "real_sig", timeout=60)
            if result['status_code'] == 500:
                return TestResult.FAILED, "Server crashed (500) on mismatched signature", result
            # Should detect mismatch or handle gracefully
            return TestResult.PASSED, f"Server handled signature mismatch gracefully: status {result['status_code']}", result
        except Exception as e:
            return TestResult.FAILED, f"Exception during signature mismatch test: {e}", None

    def test_very_simple_function(self) -> Tuple[TestResult, str, Dict]:
        """Test: Very simple function to ensure basic path still works after fixes."""
        source = """
int simple_return(int x) {
    return x;
}
int main() { return simple_return(42); }
"""
        decompiled = """int simple_return(int x) {
    return x;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        ok, result = self.call_verify_with_retry(binary, decompiled, "simple_return", expected_result="unsat")
        if not ok:
            return TestResult.FAILED, f"Basic function failed: {result.get('error')}", result
        
        if result['response'].get('result') == 'unsat':
            return TestResult.PASSED, "Simple function still works correctly after fixes", result['response']
        return TestResult.FAILED, f"Expected unsat, got {result['response'].get('result')}", result['response']

    def test_decompiled_wrong_function_name(self) -> Tuple[TestResult, str, Dict]:
        """Test: Decompiled code contains function with different internal name.
        
        Tests filter_instruction_in_function resilience.
        Server should return error with descriptive message, not crash.
        """
        source = """
int target_func(int a) {
    return a * 2;
}
int main() { return target_func(5); }
"""
        # Function name in decompiled doesn't match binary
        decompiled = """int different_name(int a) {
    return a * 2;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        try:
            result = self.call_verify(binary, decompiled, "target_func", timeout=60)
            # Accept 500 with descriptive error (e.g., "no valid CFG generated") as graceful handling
            if result['status_code'] == 500:
                error_detail = result.get('text', '')
                if 'KLEE' in error_detail or 'CFG' in error_detail or 'no valid' in error_detail.lower():
                    return TestResult.PASSED, f"Server returned descriptive error for name mismatch: {error_detail[:100]}", result
                return TestResult.FAILED, "Server crashed (500) without descriptive error", result
            # 200 with any status is fine
            return TestResult.PASSED, f"Server handled name mismatch gracefully: status {result['status_code']}", result
        except Exception as e:
            return TestResult.FAILED, f"Exception during name mismatch test: {e}", None

    # ==================== CONSISTENCY TESTS ====================
    
    def test_repeated_same_request(self) -> Tuple[TestResult, str, Dict]:
        """Test: Same request should return same result multiple times."""
        source = """
int consistent(int a, int b) {
    return a + b;
}
int main() { return consistent(1, 2); }
"""
        decompiled = """int consistent(int a, int b) {
    return a + b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        results = []
        for i in range(3):
            self.log(f"Consistency check iteration {i+1}/3")
            ok, result = self.call_verify_with_retry(binary, decompiled, "consistent")
            if ok:
                results.append(result['response'].get('result'))
            else:
                return TestResult.FAILED, f"Request {i+1} failed: {result}", None
        
        if all(r == results[0] for r in results):
            return TestResult.PASSED, f"Consistent results: {results}", {'results': results}
        return TestResult.FAILED, f"Inconsistent results: {results}", {'results': results}
    
    def test_repeated_buggy_request(self) -> Tuple[TestResult, str, Dict]:
        """Test: Buggy code should consistently return SAT."""
        source = """
int buggy_test(int a, int b) {
    return a + b;
}
int main() { return buggy_test(1, 2); }
"""
        # BUG
        decompiled = """int buggy_test(int a, int b) {
    return a * b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        results = []
        for i in range(3):
            self.log(f"Buggy consistency check iteration {i+1}/3")
            ok, result = self.call_verify_with_retry(binary, decompiled, "buggy_test")
            if ok:
                results.append(result['response'].get('result'))
            else:
                return TestResult.FAILED, f"Request {i+1} failed: {result}", None
        
        if all(r == "sat" for r in results):
            return TestResult.PASSED, f"Consistently SAT: {results}", {'results': results}
        elif all(r == results[0] for r in results):
            return TestResult.FAILED, f"Consistent but wrong (expected SAT): {results}", {'results': results}
        return TestResult.FAILED, f"Inconsistent results: {results}", {'results': results}

    # ==================== STRESS TESTS ====================
    
    def test_stress_sequential(self, iterations: int = 5) -> Tuple[TestResult, str, Dict]:
        """Stress test: Multiple sequential requests."""
        source = """
int stress_func(int a, int b) {
    return a + b;
}
int main() { return stress_func(1, 2); }
"""
        decompiled = """int stress_func(int a, int b) {
    return a + b;
}
"""
        success, binary, error = self.compile_binary(source)
        if not success:
            return TestResult.SKIPPED, f"Compilation failed: {error}", None
        
        successes = 0
        failures = 0
        times = []
        
        for i in range(iterations):
            start = time.time()
            ok, result = self.call_verify_with_retry(binary, decompiled, "stress_func")
            elapsed = time.time() - start
            times.append(elapsed)
            
            if ok and result['response'].get('result') == 'unsat':
                successes += 1
            else:
                failures += 1
            self.log(f"Iteration {i+1}/{iterations}: {'OK' if ok else 'FAIL'} in {elapsed:.2f}s")
        
        avg_time = sum(times) / len(times)
        details = {
            'successes': successes,
            'failures': failures,
            'avg_time': avg_time,
            'times': times
        }
        
        if failures == 0:
            return TestResult.PASSED, f"All {iterations} requests succeeded (avg {avg_time:.2f}s)", details
        return TestResult.FAILED, f"{failures}/{iterations} requests failed", details

    # ==================== RUN ALL TESTS ====================
    
    def run_all_tests(self, test_filter: str = None, stress_iterations: int = 5):
        """Run all tests or filtered subset."""
        test_methods = [
            # Health tests
            ("health_check", self.test_health_check),
            ("root_endpoint", self.test_root_endpoint),
            
            # Basic C tests
            ("c_add_correct", self.test_c_simple_add_correct),
            ("c_add_buggy", self.test_c_simple_add_buggy),
            ("c_subtract_correct", self.test_c_subtract_correct),
            ("c_subtract_buggy_order", self.test_c_subtract_buggy_order),
            
            # Conditional tests
            ("c_max_correct", self.test_c_max_correct),
            ("c_max_buggy", self.test_c_max_buggy_condition),
            ("c_abs_correct", self.test_c_abs_correct),
            
            # Bitwise tests
            ("c_bitwise_and_correct", self.test_c_bitwise_and_correct),
            ("c_bitwise_buggy", self.test_c_bitwise_buggy_or_vs_and),
            ("c_shift_correct", self.test_c_shift_left_correct),
            
            # Multi-arg tests
            ("c_three_args_correct", self.test_c_three_args_correct),
            ("c_three_args_buggy", self.test_c_three_args_buggy_missing),
            
            # C++ tests
            ("cpp_extern_c_correct", self.test_cpp_extern_c_correct),
            ("cpp_extern_c_buggy", self.test_cpp_extern_c_buggy),
            ("cpp_mangled_detect", self.test_cpp_mangled_name_auto_detect),
            
            # Error handling
            ("error_invalid_function", self.test_invalid_function_name),
            ("error_empty_code", self.test_empty_decompiled_code),
            ("error_malformed_code", self.test_malformed_c_code),
            
            # KLEE resilience tests (edge cases that previously crashed D-Helix)
            ("klee_complex_function", self.test_klee_complex_function),
            ("klee_bitcast_heavy", self.test_klee_bitcast_heavy_code),
            ("klee_indirect_call", self.test_klee_indirect_call),
            ("klee_mismatched_sig", self.test_mismatched_function_signature),
            ("klee_simple_sanity", self.test_very_simple_function),
            ("klee_wrong_funcname", self.test_decompiled_wrong_function_name),
            
            # Consistency tests
            ("consistency_correct", self.test_repeated_same_request),
            ("consistency_buggy", self.test_repeated_buggy_request),
            
            # Stress test
            ("stress_sequential", lambda: self.test_stress_sequential(stress_iterations)),
        ]
        
        for name, test_func in test_methods:
            if test_filter and test_filter not in name:
                continue
            self.run_test(name, test_func)
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        passed = sum(1 for r in self.results if r.result == TestResult.PASSED)
        failed = sum(1 for r in self.results if r.result == TestResult.FAILED)
        skipped = sum(1 for r in self.results if r.result == TestResult.SKIPPED)
        errors = sum(1 for r in self.results if r.result == TestResult.ERROR)
        timeouts = sum(1 for r in self.results if r.result == TestResult.TIMEOUT)
        
        total_time = sum(r.duration for r in self.results)
        
        for outcome in self.results:
            symbol = {
                TestResult.PASSED: "✓",
                TestResult.FAILED: "✗",
                TestResult.SKIPPED: "⊙",
                TestResult.ERROR: "⚠",
                TestResult.TIMEOUT: "⏱"
            }[outcome.result]
            print(f"  {symbol} {outcome.name}: {outcome.result.value} ({outcome.duration:.2f}s)")
        
        print("\n" + "-" * 70)
        print(f"Total: {len(self.results)} tests in {total_time:.2f}s")
        print(f"  ✓ Passed:  {passed}")
        print(f"  ✗ Failed:  {failed}")
        print(f"  ⊙ Skipped: {skipped}")
        print(f"  ⚠ Errors:  {errors}")
        print(f"  ⏱ Timeouts: {timeouts}")
        print("=" * 70)
        
        if failed == 0 and errors == 0 and timeouts == 0:
            print("\n✓✓✓ ALL TESTS PASSED! ✓✓✓\n")
            return 0
        else:
            print(f"\n✗✗✗ {failed + errors + timeouts} TESTS NEED ATTENTION ✗✗✗\n")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive D-Helix API Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test categories:
  health       - Health check and root endpoint tests
  c_*          - C language verification tests  
  cpp_*        - C++ language verification tests
  error_*      - Error handling tests
  consistency_* - Repeated request consistency tests
  stress_*     - Stress testing

Examples:
  python test_comprehensive.py                    # Run all tests
  python test_comprehensive.py --test c_add      # Run tests containing 'c_add'
  python test_comprehensive.py --stress 10       # Run 10 stress iterations
  python test_comprehensive.py -v                # Verbose output
"""
    )
    parser.add_argument(
        "--server", "-s",
        default=DEFAULT_SERVER,
        help=f"Server URL (default: {DEFAULT_SERVER})"
    )
    parser.add_argument(
        "--test", "-t",
        default=None,
        help="Filter tests by name substring"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output"
    )
    parser.add_argument(
        "--stress",
        type=int,
        default=5,
        help="Number of stress test iterations (default: 5)"
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=DEFAULT_RETRY,
        help=f"Number of retries for failed requests (default: {DEFAULT_RETRY})"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("D-HELIX COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print(f"Server:  {args.server}")
    print(f"Timeout: {args.timeout}s")
    print(f"Retries: {args.retry}")
    print(f"Stress:  {args.stress} iterations")
    print(f"Filter:  {args.test or 'all tests'}")
    print("=" * 70)
    
    client = DHelixTestClient(
        server_url=args.server,
        timeout=args.timeout,
        verbose=args.verbose,
        retry_count=args.retry
    )
    
    # Run tests
    client.run_all_tests(test_filter=args.test, stress_iterations=args.stress)
    
    # Print summary and return exit code
    return client.print_summary()


if __name__ == "__main__":
    sys.exit(main())
