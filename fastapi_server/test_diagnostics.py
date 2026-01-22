#!/usr/bin/env python3
"""
D-Helix Diagnostic Test Suite

Specifically designed to diagnose and reproduce:
1. Z3 execution failures (500 errors)
2. Repeated SAT results when UNSAT expected
3. KLEE processing failures
4. Angr symbolic execution issues

This suite provides detailed diagnostics to identify root causes.

Usage:
    python test_diagnostics.py [OPTIONS]
"""

import requests
import argparse
import sys
import os
import tempfile
import subprocess
import time
import json
from typing import Tuple, Dict, Any, List
from dataclasses import dataclass
import traceback

DEFAULT_SERVER = "http://localhost:10012"
DEFAULT_TIMEOUT = 180  # Longer timeout for diagnostics


@dataclass
class DiagnosticResult:
    test_name: str
    passed: bool
    api_status: int
    api_response: Dict
    duration: float
    diagnosis: str
    recommendation: str


class DHelixDiagnostics:
    """Diagnostic test client for D-Helix API issues."""
    
    def __init__(self, server_url: str, timeout: int = DEFAULT_TIMEOUT):
        self.server_url = server_url
        self.timeout = timeout
        self.results: List[DiagnosticResult] = []
    
    def compile_binary(self, source: str, is_cpp: bool = False) -> Tuple[bool, bytes, str]:
        """Compile source to binary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext = ".cpp" if is_cpp else ".c"
            src = os.path.join(tmpdir, f"src{ext}")
            out = os.path.join(tmpdir, "bin")
            
            with open(src, 'w') as f:
                f.write(source)
            
            compiler = "g++" if is_cpp else "gcc"
            result = subprocess.run(
                [compiler, "-o", out, src, "-O0", "-w"],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                return False, None, result.stderr
            
            with open(out, 'rb') as f:
                return True, f.read(), ""
    
    def call_api(self, binary: bytes, code: str, func: str, 
                 is_cpp: bool = False) -> Tuple[int, Dict, float]:
        """Call API and return (status_code, response_dict, duration)."""
        ext = ".cpp" if is_cpp else ".c"
        files = {
            'binary': ('binary', binary, 'application/octet-stream'),
            'decompiled_code': (f'{func}{ext}', code, 'text/plain')
        }
        data = {
            'function_name': func,
            'is_cpp': 'true' if is_cpp else 'false'
        }
        
        start = time.time()
        response = requests.post(
            f"{self.server_url}/verify",
            files=files, data=data,
            timeout=self.timeout
        )
        duration = time.time() - start
        
        try:
            resp_data = response.json()
        except:
            resp_data = {'raw_text': response.text}
        
        return response.status_code, resp_data, duration
    
    def diagnose_response(self, status: int, resp: Dict, expected: str) -> Tuple[str, str]:
        """Analyze response and return (diagnosis, recommendation)."""
        
        if status == 500:
            error_msg = resp.get('detail', str(resp))
            
            if 'Z3' in error_msg or 'z3' in error_msg:
                return (
                    "Z3 EXECUTION FAILURE: Z3 solver failed to execute or returned invalid result",
                    "Check: 1) Z3 binary path (/root/z3/bin/z3) exists\n"
                    "       2) Z3 formula file is being created correctly\n"
                    "       3) Z3 formula syntax is valid SMT-LIB2"
                )
            
            if 'Angr' in error_msg or 'angr' in error_msg:
                return (
                    "ANGR EXECUTION FAILURE: Angr symbolic execution failed",
                    "Check: 1) Binary is valid ELF format\n"
                    "       2) Function symbol exists in binary\n"
                    "       3) Angr can find function address"
                )
            
            if 'KLEE' in error_msg or 'klee' in error_msg:
                return (
                    "KLEE EXECUTION FAILURE: KLEE symbolic execution failed",
                    "Check: 1) LLVM bitcode was compiled correctly\n"
                    "       2) KLEE binary path (/root/PROMPT/build/bin/klee) exists\n"
                    "       3) Model file was created with correct entry point"
                )
            
            if 'compile' in error_msg.lower() or 'bitcode' in error_msg.lower():
                return (
                    "COMPILATION FAILURE: Failed to compile decompiled code to LLVM bitcode",
                    "Check: 1) Decompiled code syntax is valid C/C++\n"
                    "       2) clang path (/root/llvm-3.8/bin/clang) exists\n"
                    "       3) Required headers are available"
                )
            
            return (
                f"UNKNOWN 500 ERROR: {error_msg[:200]}",
                "Check server logs for detailed stack trace"
            )
        
        if status == 400:
            return (
                "BAD REQUEST: Invalid input to API",
                "Check: 1) Decompiled code is valid\n"
                "       2) Function name matches code"
            )
        
        if status == 200:
            result = resp.get('result')
            status_field = resp.get('status')
            
            if status_field == 'error':
                error_msg = resp.get('error_message', 'Unknown error')
                return (
                    f"API RETURNED ERROR STATUS: {error_msg}",
                    "Check server logs for the specific error"
                )
            
            if result == expected:
                return ("SUCCESS: Result matches expected", "No action needed")
            
            if expected == 'unsat' and result == 'sat':
                return (
                    "UNEXPECTED SAT: Expected UNSAT (equivalent) but got SAT (different)",
                    "Possible causes:\n"
                    "  1) KLEE symbolic execution diverged from angr\n"
                    "  2) Function preprocessing changed semantics\n"
                    "  3) Integer overflow/signedness differences\n"
                    "  4) KLEE and angr have different bit widths\n"
                    "  CHECK: Compare angr IR and KLEE IR files"
                )
            
            if expected == 'sat' and result == 'unsat':
                return (
                    "UNEXPECTED UNSAT: Expected SAT (different) but got UNSAT (equivalent)",
                    "This is usually good! But if you expected a bug to be detected:\n"
                    "  1) Bug might be in unreachable code path\n"
                    "  2) Symbolic constraints might not cover the bug case"
                )
            
            return (f"RESULT MISMATCH: Got '{result}', expected '{expected}'", "Review test case")
        
        return (f"UNEXPECTED STATUS CODE: {status}", "Check server is running correctly")
    
    def run_diagnostic(self, name: str, source: str, decompiled: str, 
                       func: str, expected: str, is_cpp: bool = False,
                       repeat: int = 1) -> List[DiagnosticResult]:
        """Run a diagnostic test, optionally multiple times."""
        print(f"\n{'='*70}")
        print(f"DIAGNOSTIC: {name}")
        print(f"{'='*70}")
        print(f"Function: {func}")
        print(f"Expected: {expected}")
        print(f"Language: {'C++' if is_cpp else 'C'}")
        if repeat > 1:
            print(f"Repeat: {repeat} times")
        
        # Compile binary
        ok, binary, err = self.compile_binary(source, is_cpp)
        if not ok:
            result = DiagnosticResult(
                test_name=name,
                passed=False,
                api_status=-1,
                api_response={'error': err},
                duration=0,
                diagnosis="COMPILATION FAILED: Could not compile test binary",
                recommendation=f"Fix source code: {err[:200]}"
            )
            self.results.append(result)
            print(f"✗ COMPILATION FAILED")
            return [result]
        
        print(f"✓ Binary compiled successfully")
        
        results = []
        for i in range(repeat):
            if repeat > 1:
                print(f"\n--- Iteration {i+1}/{repeat} ---")
            
            try:
                status, resp, duration = self.call_api(binary, decompiled, func, is_cpp)
                diagnosis, recommendation = self.diagnose_response(status, resp, expected)
                
                actual = resp.get('result') if status == 200 else None
                passed = (status == 200 and actual == expected)
                
                result = DiagnosticResult(
                    test_name=f"{name}_iter{i+1}" if repeat > 1 else name,
                    passed=passed,
                    api_status=status,
                    api_response=resp,
                    duration=duration,
                    diagnosis=diagnosis,
                    recommendation=recommendation
                )
                
                status_str = "✓ PASSED" if passed else "✗ FAILED"
                print(f"{status_str} (HTTP {status}, result={actual}, {duration:.2f}s)")
                if not passed:
                    print(f"  Diagnosis: {diagnosis}")
                    print(f"  Recommendation: {recommendation}")
                
            except requests.exceptions.Timeout:
                result = DiagnosticResult(
                    test_name=f"{name}_iter{i+1}" if repeat > 1 else name,
                    passed=False,
                    api_status=-1,
                    api_response={'error': 'timeout'},
                    duration=self.timeout,
                    diagnosis="TIMEOUT: Request exceeded timeout",
                    recommendation=f"Increase timeout (current: {self.timeout}s) or check for infinite loops"
                )
                print(f"⏱ TIMEOUT after {self.timeout}s")
                
            except Exception as e:
                result = DiagnosticResult(
                    test_name=f"{name}_iter{i+1}" if repeat > 1 else name,
                    passed=False,
                    api_status=-1,
                    api_response={'error': str(e)},
                    duration=0,
                    diagnosis=f"EXCEPTION: {str(e)}",
                    recommendation="Check network connectivity and server status"
                )
                print(f"⚠ EXCEPTION: {e}")
            
            results.append(result)
            self.results.append(result)
        
        return results
    
    # ==================== DIAGNOSTIC TESTS ====================
    
    def diag_simple_add_unsat(self, repeat: int = 3):
        """Diagnose: Simple add should consistently return UNSAT."""
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
        return self.run_diagnostic(
            "simple_add_unsat",
            source, decompiled, "add", "unsat",
            repeat=repeat
        )
    
    def diag_simple_add_sat(self, repeat: int = 3):
        """Diagnose: Buggy add (multiply) should consistently return SAT."""
        source = """
int add(int a, int b) {
    return a + b;
}
int main() { return add(1, 2); }
"""
        decompiled = """int add(int a, int b) {
    return a * b;
}
"""
        return self.run_diagnostic(
            "simple_add_sat_buggy",
            source, decompiled, "add", "sat",
            repeat=repeat
        )
    
    def diag_subtract_unsat(self, repeat: int = 3):
        """Diagnose: Subtract should return UNSAT when correct."""
        source = """
int sub(int a, int b) {
    return a - b;
}
int main() { return sub(5, 3); }
"""
        decompiled = """int sub(int a, int b) {
    return a - b;
}
"""
        return self.run_diagnostic(
            "subtract_unsat",
            source, decompiled, "sub", "unsat",
            repeat=repeat
        )
    
    def diag_conditional_unsat(self, repeat: int = 3):
        """Diagnose: Conditional (max) should return UNSAT when correct."""
        source = """
int my_max(int a, int b) {
    if (a > b) return a;
    return b;
}
int main() { return my_max(5, 3); }
"""
        decompiled = """int my_max(int a, int b) {
    if (a > b) return a;
    return b;
}
"""
        return self.run_diagnostic(
            "conditional_max_unsat",
            source, decompiled, "my_max", "unsat",
            repeat=repeat
        )
    
    def diag_conditional_sat(self, repeat: int = 3):
        """Diagnose: Wrong conditional should return SAT."""
        source = """
int my_max(int a, int b) {
    if (a > b) return a;
    return b;
}
int main() { return my_max(5, 3); }
"""
        # BUG: returns min instead of max
        decompiled = """int my_max(int a, int b) {
    if (a < b) return a;
    return b;
}
"""
        return self.run_diagnostic(
            "conditional_max_sat_buggy",
            source, decompiled, "my_max", "sat",
            repeat=repeat
        )
    
    def diag_bitwise_unsat(self, repeat: int = 3):
        """Diagnose: Bitwise operations."""
        source = """
int my_and(int a, int b) {
    return a & b;
}
int main() { return my_and(5, 3); }
"""
        decompiled = """int my_and(int a, int b) {
    return a & b;
}
"""
        return self.run_diagnostic(
            "bitwise_and_unsat",
            source, decompiled, "my_and", "unsat",
            repeat=repeat
        )
    
    def diag_cpp_extern_c(self, repeat: int = 3):
        """Diagnose: C++ extern C function."""
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
        return self.run_diagnostic(
            "cpp_extern_c_unsat",
            source, decompiled, "cpp_add", "unsat",
            is_cpp=True, repeat=repeat
        )
    
    def diag_z3_stress(self, iterations: int = 10):
        """Diagnose: Z3 under stress (many rapid requests)."""
        print(f"\n{'='*70}")
        print(f"Z3 STRESS TEST: {iterations} rapid sequential requests")
        print(f"{'='*70}")
        
        source = """
int stress(int a, int b) {
    return a + b;
}
int main() { return stress(1, 2); }
"""
        decompiled = """int stress(int a, int b) {
    return a + b;
}
"""
        
        ok, binary, err = self.compile_binary(source)
        if not ok:
            print(f"✗ Compilation failed: {err}")
            return
        
        successes = 0
        failures = 0
        z3_errors = 0
        timeouts = 0
        
        for i in range(iterations):
            try:
                status, resp, duration = self.call_api(binary, decompiled, "stress")
                
                if status == 200 and resp.get('result') == 'unsat':
                    successes += 1
                    print(f"  {i+1}/{iterations}: ✓ UNSAT ({duration:.2f}s)")
                elif status == 500:
                    failures += 1
                    detail = resp.get('detail', str(resp))
                    if 'z3' in detail.lower() or 'Z3' in detail:
                        z3_errors += 1
                        print(f"  {i+1}/{iterations}: ✗ Z3 ERROR ({duration:.2f}s)")
                    else:
                        print(f"  {i+1}/{iterations}: ✗ 500 ERROR ({duration:.2f}s)")
                else:
                    failures += 1
                    print(f"  {i+1}/{iterations}: ✗ {status} {resp.get('result')} ({duration:.2f}s)")
                    
            except requests.exceptions.Timeout:
                timeouts += 1
                print(f"  {i+1}/{iterations}: ⏱ TIMEOUT")
            except Exception as e:
                failures += 1
                print(f"  {i+1}/{iterations}: ⚠ EXCEPTION: {e}")
        
        print(f"\nSTRESS TEST SUMMARY:")
        print(f"  Successes: {successes}/{iterations}")
        print(f"  Failures:  {failures}/{iterations}")
        print(f"  Z3 Errors: {z3_errors}/{iterations}")
        print(f"  Timeouts:  {timeouts}/{iterations}")
        
        if z3_errors > 0:
            print(f"\n⚠ Z3 ERRORS DETECTED!")
            print(f"  Recommendation: Check Z3 installation and formula generation")
        
        if successes == iterations:
            print(f"\n✓ STRESS TEST PASSED!")
        else:
            print(f"\n✗ STRESS TEST FAILED: {100*failures/iterations:.1f}% failure rate")
    
    def diag_sat_consistency(self, iterations: int = 5):
        """Diagnose: SAT results should be consistent."""
        print(f"\n{'='*70}")
        print(f"SAT CONSISTENCY TEST: Buggy code should consistently return SAT")
        print(f"{'='*70}")
        
        source = """
int buggy(int a, int b) {
    return a + b;
}
int main() { return buggy(1, 2); }
"""
        # BUG: different operation
        decompiled = """int buggy(int a, int b) {
    return a * b;
}
"""
        
        results = self.run_diagnostic(
            "sat_consistency",
            source, decompiled, "buggy", "sat",
            repeat=iterations
        )
        
        sat_count = sum(1 for r in results if r.api_response.get('result') == 'sat')
        unsat_count = sum(1 for r in results if r.api_response.get('result') == 'unsat')
        error_count = sum(1 for r in results if r.api_status != 200)
        
        print(f"\nCONSISTENCY ANALYSIS:")
        print(f"  SAT results:   {sat_count}/{iterations} (expected: {iterations})")
        print(f"  UNSAT results: {unsat_count}/{iterations} (expected: 0)")
        print(f"  Errors:        {error_count}/{iterations}")
        
        if sat_count == iterations:
            print(f"\n✓ SAT CONSISTENCY PASSED!")
        elif unsat_count > 0:
            print(f"\n✗ INCONSISTENT: Got UNSAT when SAT expected!")
            print(f"  This indicates non-determinism in the symbolic execution")
        else:
            print(f"\n✗ SAT CONSISTENCY FAILED due to errors")
    
    def run_all_diagnostics(self, repeat: int = 3):
        """Run all diagnostic tests."""
        print("\n" + "=" * 70)
        print("D-HELIX DIAGNOSTIC SUITE")
        print("=" * 70)
        print(f"Server:  {self.server_url}")
        print(f"Timeout: {self.timeout}s")
        print(f"Repeat:  {repeat} times per test")
        
        # Check server health first
        try:
            resp = requests.get(f"{self.server_url}/health", timeout=5)
            if resp.status_code != 200:
                print(f"\n✗ Server health check failed: {resp.status_code}")
                return
            print(f"✓ Server is healthy")
        except Exception as e:
            print(f"\n✗ Cannot reach server: {e}")
            return
        
        # Run diagnostics
        self.diag_simple_add_unsat(repeat)
        self.diag_simple_add_sat(repeat)
        self.diag_subtract_unsat(repeat)
        self.diag_conditional_unsat(repeat)
        self.diag_conditional_sat(repeat)
        self.diag_bitwise_unsat(repeat)
        self.diag_cpp_extern_c(repeat)
        
        # Stress tests
        self.diag_z3_stress(10)
        self.diag_sat_consistency(5)
        
        # Final summary
        self.print_summary()
    
    def print_summary(self):
        """Print diagnostic summary."""
        print("\n" + "=" * 70)
        print("DIAGNOSTIC SUMMARY")
        print("=" * 70)
        
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        # Group by diagnosis type
        diagnosis_counts = {}
        for r in self.results:
            if not r.passed:
                key = r.diagnosis.split(':')[0]
                diagnosis_counts[key] = diagnosis_counts.get(key, 0) + 1
        
        print(f"\nTotal tests: {len(self.results)}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        
        if diagnosis_counts:
            print(f"\nFailure breakdown:")
            for diag, count in sorted(diagnosis_counts.items(), key=lambda x: -x[1]):
                print(f"  {diag}: {count}")
        
        # Specific recommendations
        print("\n" + "-" * 70)
        print("RECOMMENDATIONS:")
        
        if any('Z3' in r.diagnosis for r in self.results if not r.passed):
            print("""
[Z3 ISSUES DETECTED]
1. Verify Z3 installation: /root/z3/bin/z3 --version
2. Check Z3 formula files are being created in work directory
3. Review formula syntax - look for invalid SMT-LIB2
4. Consider increasing Z3 timeout
""")
        
        if any('UNEXPECTED SAT' in r.diagnosis for r in self.results if not r.passed):
            print("""
[UNEXPECTED SAT RESULTS]
1. Compare angr IR vs KLEE IR files for differences
2. Check function preprocessing (headers, typedefs)
3. Verify symbolic argument setup matches between angr and KLEE
4. Look for integer overflow/signedness issues
""")
        
        if any('TIMEOUT' in r.diagnosis for r in self.results if not r.passed):
            print("""
[TIMEOUT ISSUES]
1. Increase timeout (--timeout flag)
2. Check for infinite loops in symbolic execution
3. Consider simpler test cases
4. Monitor server resource usage
""")
        
        if passed == len(self.results):
            print("\n✓✓✓ ALL DIAGNOSTICS PASSED! ✓✓✓")
            return 0
        else:
            print(f"\n✗✗✗ {failed} DIAGNOSTICS NEED ATTENTION ✗✗✗")
            return 1


def main():
    parser = argparse.ArgumentParser(description="D-Helix Diagnostic Test Suite")
    parser.add_argument("--server", "-s", default=DEFAULT_SERVER, help="Server URL")
    parser.add_argument("--timeout", "-t", type=int, default=DEFAULT_TIMEOUT, help="Timeout (seconds)")
    parser.add_argument("--repeat", "-r", type=int, default=3, help="Repeat each test N times")
    parser.add_argument("--test", choices=[
        'add_unsat', 'add_sat', 'subtract', 'conditional_unsat', 'conditional_sat',
        'bitwise', 'cpp', 'z3_stress', 'sat_consistency', 'all'
    ], default='all', help="Specific test to run")
    
    args = parser.parse_args()
    
    diag = DHelixDiagnostics(args.server, args.timeout)
    
    test_map = {
        'add_unsat': diag.diag_simple_add_unsat,
        'add_sat': diag.diag_simple_add_sat,
        'subtract': diag.diag_subtract_unsat,
        'conditional_unsat': diag.diag_conditional_unsat,
        'conditional_sat': diag.diag_conditional_sat,
        'bitwise': diag.diag_bitwise_unsat,
        'cpp': diag.diag_cpp_extern_c,
        'z3_stress': lambda r=10: diag.diag_z3_stress(r),
        'sat_consistency': lambda r=5: diag.diag_sat_consistency(r),
    }
    
    if args.test == 'all':
        diag.run_all_diagnostics(args.repeat)
    else:
        test_func = test_map.get(args.test)
        if test_func:
            test_func(args.repeat)
            diag.print_summary()
    
    return 0 if all(r.passed for r in diag.results) else 1


if __name__ == "__main__":
    sys.exit(main())
