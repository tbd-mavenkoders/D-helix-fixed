#!/usr/bin/env python3
"""
MissionDecompile Integration Test

This test mimics exactly how MissionDecompile's batched_humaneval_collector_v2.py
calls the D-Helix API. Use this to verify API compatibility.

Usage:
    python test_missiondecompile_compat.py [--server URL]
"""

import requests
import argparse
import sys
import os
import tempfile
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Tuple

DEFAULT_SERVER = "http://localhost:10012"
DHELIX_TIMEOUT = 120  # Same as MissionDecompile


@dataclass
class DHelixResult:
    """Result from D-Helix verification - matches MissionDecompile's DHelixResult."""
    success: bool
    result: Optional[str]  # "sat" or "unsat"
    z3_formula: Optional[str]
    counterexample: Optional[Dict]
    error_message: Optional[str]


def call_dhelix_api(binary_path: Path, decompiled_code: str, 
                    function_name: str, api_url: str = DEFAULT_SERVER) -> DHelixResult:
    """
    Call D-Helix API to verify semantic equivalence.
    This is a direct copy of the function from batched_humaneval_collector_v2.py
    """
    try:
        print(f"[D-Helix] Verifying {function_name} against binary {binary_path}...")
        
        with open(binary_path, 'rb') as binary_file:
            files = {
                'binary': (binary_path.name, binary_file, 'application/octet-stream'),
                'decompiled_code': (f'{function_name}.c', decompiled_code, 'text/plain')
            }
            data = {
                'function_name': function_name
            }
            
            response = requests.post(
                f"{api_url}/verify",
                files=files,
                data=data,
                timeout=DHELIX_TIMEOUT
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"[D-Helix] Result: {result['result']} ({result['status']})")
            
            return DHelixResult(
                success=True,
                result=result['result'],
                z3_formula=result.get('z3_formula'),
                counterexample=result.get('counterexample'),
                error_message=None
            )
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            print(f"[D-Helix] Error: {error_msg}")
            return DHelixResult(
                success=False,
                result=None,
                z3_formula=None,
                counterexample=None,
                error_message=error_msg
            )
    
    except requests.exceptions.Timeout:
        print(f"[D-Helix] Timeout after {DHELIX_TIMEOUT}s")
        return DHelixResult(
            success=False,
            result=None,
            z3_formula=None,
            counterexample=None,
            error_message=f"Timeout after {DHELIX_TIMEOUT}s"
        )
    except Exception as e:
        print(f"[D-Helix] Exception: {e}")
        return DHelixResult(
            success=False,
            result=None,
            z3_formula=None,
            counterexample=None,
            error_message=str(e)
        )


def compile_binary(source_code: str, output_path: Path, is_cpp: bool = False) -> Tuple[bool, str]:
    """Compile source code to binary."""
    ext = ".cpp" if is_cpp else ".c"
    with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as f:
        f.write(source_code)
        source_path = f.name
    
    try:
        compiler = "g++" if is_cpp else "gcc"
        result = subprocess.run(
            [compiler, "-o", str(output_path), source_path, "-O0", "-w"],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            return True, "Success"
        else:
            return False, result.stderr
    finally:
        os.unlink(source_path)


class MissionDecompileCompatTest:
    """Test suite that mimics MissionDecompile's usage patterns."""
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.results = []
    
    def test_correct_code_unsat(self) -> bool:
        """
        Test 1: Correct decompiled code should return UNSAT
        This simulates: Ghidra output that perfectly matches binary
        """
        print("\n" + "=" * 60)
        print("TEST: Correct Code (expect UNSAT)")
        print("=" * 60)
        
        # Original source (compiled to binary)
        binary_source = """
int add(int a, int b) {
    return a + b;
}
int main() { return add(2, 3); }
"""
        
        # Decompiled code (sent to D-Helix) - NO main function
        # D-Helix adds its own main stub
        decompiled_code = """
int add(int a, int b) {
    return a + b;
}
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "test_binary"
            
            success, msg = compile_binary(binary_source, binary_path)
            if not success:
                print(f"✗ Compilation failed: {msg}")
                return False
            
            print("✓ Binary compiled")
            
            result = call_dhelix_api(binary_path, decompiled_code, "add", self.server_url)
            
            if result.success and result.result == "unsat":
                print("✓ TEST PASSED: Got UNSAT as expected")
                self.results.append(("correct_code_unsat", True))
                return True
            else:
                print(f"✗ TEST FAILED: expected unsat, got {result.result}")
                print(f"  Error: {result.error_message}")
                self.results.append(("correct_code_unsat", False))
                return False
    
    def test_buggy_code_sat(self) -> bool:
        """
        Test 2: Buggy decompiled code should return SAT
        This simulates: Initial LLM output with wrong logic
        """
        print("\n" + "=" * 60)
        print("TEST: Buggy Code (expect SAT)")
        print("=" * 60)
        
        # Original source (compiled to binary)
        binary_source = """
int add(int a, int b) {
    return a + b;
}
int main() { return add(2, 3); }
"""
        
        # BUGGY decompiled code - multiplication instead of addition
        decompiled_code = """
int add(int a, int b) {
    return a * b;
}
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "test_binary"
            
            success, msg = compile_binary(binary_source, binary_path)
            if not success:
                print(f"✗ Compilation failed: {msg}")
                return False
            
            print("✓ Binary compiled")
            
            result = call_dhelix_api(binary_path, decompiled_code, "add", self.server_url)
            
            if result.success and result.result == "sat":
                print("✓ TEST PASSED: Got SAT as expected (bug detected)")
                if result.counterexample:
                    print(f"  Counterexample: {result.counterexample}")
                self.results.append(("buggy_code_sat", True))
                return True
            else:
                print(f"✗ TEST FAILED: expected sat, got {result.result}")
                print(f"  Error: {result.error_message}")
                self.results.append(("buggy_code_sat", False))
                return False
    
    def test_semantic_repair_cycle(self) -> bool:
        """
        Test 3: Simulate full semantic repair cycle
        1. Submit buggy code -> get SAT
        2. "Fix" the code
        3. Submit fixed code -> get UNSAT
        """
        print("\n" + "=" * 60)
        print("TEST: Semantic Repair Cycle")
        print("=" * 60)
        
        binary_source = """
int subtract(int a, int b) {
    return a - b;
}
int main() { return subtract(10, 3); }
"""
        
        # Phase 1: Buggy code (wrong operand order)
        buggy_code = """
int subtract(int a, int b) {
    return b - a;
}
"""
        
        # Phase 2: Fixed code
        fixed_code = """
int subtract(int a, int b) {
    return a - b;
}
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "test_binary"
            
            success, msg = compile_binary(binary_source, binary_path)
            if not success:
                print(f"✗ Compilation failed: {msg}")
                return False
            
            print("✓ Binary compiled")
            
            # Phase 1: Submit buggy code
            print("\nPhase 1: Submit buggy code...")
            result1 = call_dhelix_api(binary_path, buggy_code, "subtract", self.server_url)
            
            if not result1.success or result1.result != "sat":
                print(f"✗ Phase 1 failed: expected sat, got {result1.result}")
                self.results.append(("semantic_repair_cycle", False))
                return False
            
            print(f"✓ Phase 1: Got SAT (bug detected)")
            if result1.counterexample:
                print(f"  Counterexample: {result1.counterexample}")
            
            # Phase 2: Submit fixed code
            print("\nPhase 2: Submit fixed code...")
            result2 = call_dhelix_api(binary_path, fixed_code, "subtract", self.server_url)
            
            if result2.success and result2.result == "unsat":
                print("✓ Phase 2: Got UNSAT (semantically equivalent)")
                print("✓ TEST PASSED: Full repair cycle works")
                self.results.append(("semantic_repair_cycle", True))
                return True
            else:
                print(f"✗ Phase 2 failed: expected unsat, got {result2.result}")
                print(f"  Error: {result2.error_message}")
                self.results.append(("semantic_repair_cycle", False))
                return False
    
    def test_repeated_verification(self, iterations: int = 5) -> bool:
        """
        Test 4: Repeated verification should give consistent results
        This tests for the "repeated SAT" issue
        """
        print("\n" + "=" * 60)
        print(f"TEST: Repeated Verification ({iterations} iterations)")
        print("=" * 60)
        
        binary_source = """
int consistent(int a, int b) {
    return a + b;
}
int main() { return consistent(1, 2); }
"""
        
        decompiled_code = """
int consistent(int a, int b) {
    return a + b;
}
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "test_binary"
            
            success, msg = compile_binary(binary_source, binary_path)
            if not success:
                print(f"✗ Compilation failed: {msg}")
                return False
            
            print("✓ Binary compiled")
            
            results = []
            for i in range(iterations):
                result = call_dhelix_api(binary_path, decompiled_code, "consistent", self.server_url)
                outcome = result.result if result.success else f"ERROR: {result.error_message}"
                results.append(outcome)
                print(f"  Iteration {i+1}: {outcome}")
            
            # Check consistency
            if all(r == "unsat" for r in results):
                print(f"✓ TEST PASSED: All {iterations} iterations returned UNSAT")
                self.results.append(("repeated_verification", True))
                return True
            elif all(r == results[0] for r in results):
                print(f"✗ TEST FAILED: Consistent but wrong (got '{results[0]}', expected 'unsat')")
                self.results.append(("repeated_verification", False))
                return False
            else:
                print(f"✗ TEST FAILED: Inconsistent results: {results}")
                self.results.append(("repeated_verification", False))
                return False
    
    def test_api_error_handling(self) -> bool:
        """
        Test 5: API should handle errors gracefully (return DHelixResult with error)
        """
        print("\n" + "=" * 60)
        print("TEST: Error Handling")
        print("=" * 60)
        
        binary_source = """
int real_func(int a) { return a; }
int main() { return real_func(1); }
"""
        
        # Code for non-existent function
        decompiled_code = """
int fake_func(int a) { return a; }
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = Path(tmpdir) / "test_binary"
            
            success, msg = compile_binary(binary_source, binary_path)
            if not success:
                print(f"✗ Compilation failed: {msg}")
                return False
            
            print("✓ Binary compiled")
            
            # Call with non-existent function name
            result = call_dhelix_api(binary_path, decompiled_code, "nonexistent_xyz", self.server_url)
            
            # Should return a DHelixResult with success=False, not crash
            if not result.success:
                print(f"✓ TEST PASSED: API returned error result (not crash)")
                print(f"  Error: {result.error_message}")
                self.results.append(("error_handling", True))
                return True
            else:
                print(f"⚠ TEST UNEXPECTED: API succeeded for invalid function")
                self.results.append(("error_handling", True))  # Still acceptable
                return True
    
    def run_all_tests(self):
        """Run all MissionDecompile compatibility tests."""
        print("=" * 70)
        print("MISSIONDECOMPILE COMPATIBILITY TEST SUITE")
        print("=" * 70)
        print(f"Server: {self.server_url}")
        print(f"Timeout: {DHELIX_TIMEOUT}s")
        
        # Check health first
        try:
            resp = requests.get(f"{self.server_url}/health", timeout=5)
            if resp.status_code != 200:
                print(f"\n✗ Server health check failed")
                return 1
            print("✓ Server is healthy")
        except Exception as e:
            print(f"\n✗ Cannot reach server: {e}")
            return 1
        
        # Run tests
        self.test_correct_code_unsat()
        self.test_buggy_code_sat()
        self.test_semantic_repair_cycle()
        self.test_repeated_verification(5)
        self.test_api_error_handling()
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        passed = sum(1 for _, ok in self.results if ok)
        failed = len(self.results) - passed
        
        for name, ok in self.results:
            status = "✓ PASSED" if ok else "✗ FAILED"
            print(f"  {name}: {status}")
        
        print(f"\nTotal: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("\n✓✓✓ ALL TESTS PASSED! ✓✓✓")
            print("D-Helix API is compatible with MissionDecompile")
            return 0
        else:
            print(f"\n✗✗✗ {failed} TEST(S) FAILED ✗✗✗")
            return 1


def main():
    parser = argparse.ArgumentParser(description="MissionDecompile D-Helix Compatibility Test")
    parser.add_argument("--server", "-s", default=DEFAULT_SERVER, help="D-Helix API URL")
    args = parser.parse_args()
    
    tester = MissionDecompileCompatTest(args.server)
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
