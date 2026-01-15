#!/bin/bash
# Extract concrete input values for all detected bugs

echo "=== D-Helix Bug Counterexamples ==="
echo

for bug_file in $(cat diff_result 2>/dev/null | grep "is wrong:" | cut -d' ' -f1); do
    echo "Bug: $bug_file"
    z3_file="./test_muqi/z3/$bug_file"
    
    if [ -f "$z3_file" ]; then
        echo "Input values that trigger this bug:"
        echo "(get-model)" | cat "$z3_file" - | z3 -in | grep -A1 "define-fun" | sed 's/^/  /'
    else
        echo "  Z3 file not found"
    fi
    echo
done
