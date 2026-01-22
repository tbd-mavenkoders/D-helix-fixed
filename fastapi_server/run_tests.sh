#!/bin/bash
# D-Helix API Test Runner
# Runs all test suites for the D-Helix FastAPI server

set -e

# Configuration
SERVER_URL="${DHELIX_SERVER_URL:-http://localhost:10012}"
TEST_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=================================================="
echo "D-HELIX API TEST RUNNER"
echo "=================================================="
echo "Server: $SERVER_URL"
echo "Test Dir: $TEST_DIR"
echo ""

# Check if server is running
echo "Checking server health..."
if curl -s "$SERVER_URL/health" > /dev/null 2>&1; then
    echo "✓ Server is running"
else
    echo "✗ Server is not responding at $SERVER_URL"
    echo ""
    echo "Please start the server first:"
    echo "  cd $TEST_DIR && python api_server.py"
    exit 1
fi

echo ""

# Function to run a test and capture result
run_test() {
    local name="$1"
    local script="$2"
    local args="${3:-}"
    
    echo "=================================================="
    echo "Running: $name"
    echo "=================================================="
    
    if python "$TEST_DIR/$script" --server "$SERVER_URL" $args; then
        echo "✓ $name: PASSED"
        return 0
    else
        echo "✗ $name: FAILED"
        return 1
    fi
}

# Track results
PASSED=0
FAILED=0

# Run test suites based on arguments
case "${1:-all}" in
    quick)
        # Quick sanity check
        run_test "Quick Test" "test_client.py" && ((PASSED++)) || ((FAILED++))
        ;;
    
    compat)
        # MissionDecompile compatibility test
        run_test "MissionDecompile Compatibility" "test_missiondecompile_compat.py" && ((PASSED++)) || ((FAILED++))
        ;;
    
    comprehensive)
        # Full comprehensive test suite
        run_test "Comprehensive Test Suite" "test_comprehensive.py" && ((PASSED++)) || ((FAILED++))
        ;;
    
    diagnostics)
        # Diagnostic tests for debugging issues
        run_test "Diagnostic Suite" "test_diagnostics.py" "--repeat 3" && ((PASSED++)) || ((FAILED++))
        ;;
    
    stress)
        # Stress testing
        run_test "Stress Test" "test_comprehensive.py" "--test stress --stress 20" && ((PASSED++)) || ((FAILED++))
        ;;
    
    all)
        # Run all test suites
        echo "Running ALL test suites..."
        echo ""
        
        run_test "Quick Test" "test_client.py" && ((PASSED++)) || ((FAILED++))
        echo ""
        
        run_test "MissionDecompile Compatibility" "test_missiondecompile_compat.py" && ((PASSED++)) || ((FAILED++))
        echo ""
        
        run_test "Comprehensive Test Suite" "test_comprehensive.py" && ((PASSED++)) || ((FAILED++))
        ;;
    
    *)
        echo "Usage: $0 [quick|compat|comprehensive|diagnostics|stress|all]"
        echo ""
        echo "  quick          - Quick sanity check (test_client.py)"
        echo "  compat         - MissionDecompile compatibility tests"
        echo "  comprehensive  - Full test suite with many scenarios"
        echo "  diagnostics    - Detailed diagnostics for debugging issues"
        echo "  stress         - Stress testing with many iterations"
        echo "  all            - Run all test suites (default)"
        exit 1
        ;;
esac

echo ""
echo "=================================================="
echo "FINAL RESULTS"
echo "=================================================="
echo "Passed: $PASSED"
echo "Failed: $FAILED"

if [ $FAILED -eq 0 ]; then
    echo ""
    echo "✓✓✓ ALL TEST SUITES PASSED! ✓✓✓"
    exit 0
else
    echo ""
    echo "✗✗✗ SOME TEST SUITES FAILED ✗✗✗"
    exit 1
fi
