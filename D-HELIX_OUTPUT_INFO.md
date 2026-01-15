# D-Helix Output Information for Tuner/Validator

## Summary
D-Helix performs **symbolic differentiation** to detect decompilation bugs by comparing the semantic behavior of original binary functions against their decompiled versions. It outputs **sat/unsat** results that indicate whether the decompiled code is semantically equivalent to the original.

---

## 1. Primary Output: Bug Detection Results

### Location
- **Final Report**: `./diff_result`
- **Individual Results**: `./test_muqi/diff/<function_name>_z3[_unsat]`

### Output Format
```
<function_name>_z3[_unsat] is wrong: 
in diff: 
sat
```

### Interpretation
- **sat** = Decompilation bug detected (semantic difference exists)
- **unsat** = Correct decompilation (semantically equivalent)

The naming convention:
- `*_z3_unsat` files: Expected result is "unsat" (correct decompilation)
- `*_z3` files (no suffix): Expected result is "sat" (known to differ)

**Bug is reported when**: actual result ≠ expected result

---

## 2. Detailed Artifacts Generated Per Function

### A. Decompiled Source Code
**Location**: `./test_muqi/generated_function_c/project_folder/<binary>_folder/<binary>_<function>.c`

**Content**: Angr-decompiled C code with:
- Function signature
- Local variables
- Decompiled logic
- Compiler-friendly modifications (global variable declarations, type definitions)

**Example**:
```c
int multiply(unsigned long a0, unsigned long a1)
{
    unsigned int v0;
    unsigned int v1;
    char v2;
    unsigned long long v4;

    v1 = ((int)a0);
    v0 = ((int)a1);
    v4 = &v2;
    return;  // BUG: Missing return value calculation!
}
```

---

### B. LLVM Bitcode
**Location**: `./test_muqi/generatedbc/<binary>_<function>.bc`

**Purpose**: Compiled decompiled code for KLEE symbolic execution

**Usage**: Can be analyzed with LLVM tools (`llvm-dis`, `opt`, etc.)

---

### C. KLEE Execution Logs
**Locations**:
- **Standard output**: `./test_muqi/log_klee/log_klee<binary>_<function>.txt`
- **Error output**: `./test_muqi/log_klee/log_klee<binary>_<function>_error.txt`

**Content**:
- Symbolic variable bindings
- Execution states
- Path exploration details
- Termination status

**Key line**: `terminating state with <function>` indicates successful completion

---

### D. Angr Symbolic Execution Trace
**Location**: `/tmp/angr_<binary>_<function>.txt`

**Content**:
- Basic block addresses and ranges
- Symbolic expressions for each execution path
- Z3 constraint formulas for binary behavior

**Example**:
```
Filename:  ./test_muqi/originalclang/test_buggy
Function:  multiply
BasicBlock_cfg:[0x401110 -> 0x401125]
----dump z3 start----
; benchmark
(declare-fun angr_arg1_38_64 () (_ BitVec 64))
(declare-fun angr_arg0_37_64 () (_ BitVec 64))
(let ((?x34 ((_ extract 31 0) angr_arg1_38_64)))
 (let ((?x35 ((_ extract 31 0) angr_arg0_37_64)))
 (let ((?x38 (bvmul ?x35 ?x34)))
 (concat (_ bv0 32) ?x38))))
----dump z3 end----
```

---

### E. Intermediate Representations (IR)
**Locations**:
- `/tmp/angr_<binary>_<function>_ir_first.txt`
- `/tmp/angr_<binary>_<function>_ir_second.txt`
- `/tmp/angr_<binary>_<function>_ir_third.txt`
- `/tmp/angr_<binary>_<function>_ir_third_flip.txt` (final canonical form)

**Content**: Progressive transformations of Angr's symbolic expressions into Z3-compatible format

---

### F. Z3 SMT Formulas
**Location**: `./test_muqi/z3/<binary>_<function>_z3[_unsat]`

**Content**: Complete SMT-LIB2 formula comparing binary vs decompiled behavior

**Structure**:
```smt2
(declare-const angr_arg0_37_64 (_ BitVec 64))
(declare-const angr_arg1_38_64 (_ BitVec 64))
(assert 
  (let ((angr <angr_expression>))
    (let ((prompt <klee_expression>))
      (not (= angr prompt))
    )
  )
)
```

**Key**: Asserts that angr ≠ prompt, so:
- **sat** = difference exists (bug)
- **unsat** = no difference possible (correct)

---

### G. KLEE Model Files
**Location**: `./test_muqi/model_prompt/model<binary>_<function>.txt`

**Content**: PROMPT (KLEE variant) API model specification
```
global settings:
data models:
function models:
lifecycle model:
    entry-point <function_name>
```

---

### H. Compilation Logs
**Location**: `./test_muqi/generated_function_c/log_for_compile/<binary>_folder/<binary>_<function>.txt`

**Content**: Clang compiler output when compiling decompiled code
- Compilation errors/warnings
- Syntax issues in decompiled code
- Type mismatches

---

## 3. Extracting Counterexamples (Concrete Input Values)

When Z3 returns **sat** (bug detected), you can extract concrete input values that demonstrate the semantic difference:

### Command
```bash
echo "(get-model)" | cat ./test_muqi/z3/<function>_z3_unsat - | z3 -in
```

### Example Output
```
sat
(
  (define-fun angr_arg0_37_64 () (_ BitVec 64)
    #x00000000ffffffff)
  (define-fun angr_arg1_38_64 () (_ BitVec 64)
    #x0000000000000001)
)
```

**Interpretation**: When calling `multiply(0xFFFFFFFF, 0x1)`:
- Original binary: Returns `0xFFFFFFFF * 0x1 = 0xFFFFFFFF`
- Decompiled code: Returns nothing (bug!)

---

## 4. Information NOT Currently Generated

D-Helix does **NOT** automatically provide:

1. **Concrete counterexamples** - Must manually run `z3 -model` on Z3 files
2. **Test cases** - No automatic test generation for bug reproduction
3. **Bug categorization** - Doesn't classify bug types (missing return, wrong operator, etc.)
4. **Confidence scores** - Binary result only (sat/unsat)
5. **Execution coverage metrics** - No path coverage statistics
6. **Performance metrics** - No timing information per function

---

## 5. Useful Information for Tuner/Validator

### A. Files to Parse for Automated Analysis

1. **`./diff_result`** - List of detected bugs with function names
2. **`./test_muqi/diff/*`** - Individual sat/unsat results
3. **`./test_muqi/z3/*`** - SMT formulas (can extract with `get-model`)
4. **`./test_muqi/generated_function_c/project_folder/*/`** - Decompiled source code

### B. Extracting Structured Data

```python
# Parse diff_result to get bug list
with open('./diff_result', 'r') as f:
    bugs = []
    for line in f:
        if 'is wrong:' in line:
            func_name = line.split('_z3')[0]
            bugs.append(func_name)

# For each bug, extract counterexample
import subprocess
for bug in bugs:
    z3_file = f"./test_muqi/z3/{bug}_z3_unsat"
    cmd = f'echo "(get-model)" | cat {z3_file} - | z3 -in'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if 'sat' in result.stdout:
        # Parse model from result.stdout
        print(f"{bug}: {result.stdout}")
```

### C. Filtering Strategy (check_diff.py logic)

The script filters out:
- **Void functions** - No return value to compare
- **Functions returning pointers** - May have aliasing issues
- **Functions with doubles/floats** - Floating-point comparison issues
- **Functions with same block IDs** - Control flow anomalies

These filters reduce false positives.

---

## 6. Enhancing D-Helix Output for Validation

To make D-Helix more useful for automated validation, consider adding:

1. **Automatic counterexample extraction** in `generate_symbolic.py` after Z3 execution
2. **JSON output format** with structured bug reports
3. **Test case generation** using KLEE's concrete test vectors
4. **Bug type classification** (missing return, wrong operation, control flow error)
5. **Confidence scoring** based on path coverage and constraint complexity

---

## 7. Current Limitations

1. **No incremental analysis** - Full re-run required for changes
2. **Caching bug** (identified) - May skip functions on re-runs if model files are missing
3. **No parallel Z3 solving** - Sequential processing of Z3 files
4. **Limited error context** - Doesn't pinpoint exact source line causing semantic difference
5. **No regression tracking** - Doesn't compare results across runs

---

## Example: Complete Bug Analysis Workflow

```bash
# 1. Run D-Helix
python generate_symbolic.py

# 2. Check detected bugs
cat diff_result
# Output: test_buggy_multiply_z3_unsat is wrong

# 3. View decompiled code
cat test_muqi/generated_function_c/project_folder/test_buggy_folder/test_buggy_multiply.c
# Shows: return; with no value!

# 4. Extract counterexample
echo "(get-model)" | cat test_muqi/z3/test_buggy_multiply_z3_unsat - | z3 -in
# Output: arg0=0xFFFFFFFF, arg1=0x1

# 5. Verify manually
./test_muqi/originalclang/test_buggy
# Input: multiply(0xFFFFFFFF, 0x1)
# Expected: 0xFFFFFFFF
# Decompiled: returns garbage (undefined behavior)

# 6. Parse all bugs programmatically
python check_diff.py
# Generates: ./diff_result with filtered results
```

---

## Summary Table

| Artifact | Location | Contains | Useful For |
|----------|----------|----------|------------|
| Bug Report | `./diff_result` | List of functions with semantic bugs | Bug tracking |
| Sat/Unsat | `./test_muqi/diff/*` | Individual Z3 results | Validation ground truth |
| Decompiled Code | `./test_muqi/generated_function_c/project_folder/*/` | C source from Angr | Understanding bug context |
| Z3 Formulas | `./test_muqi/z3/*` | SMT constraints | Extracting counterexamples |
| KLEE Logs | `./test_muqi/log_klee/*` | Symbolic execution trace | Debugging KLEE issues |
| Angr Logs | `/tmp/angr_*` | Binary execution trace | Understanding binary behavior |
| Bitcode | `./test_muqi/generatedbc/*` | Compiled decompiled code | LLVM-based analysis |

**Key Takeaway**: D-Helix provides **binary bug detection** (sat/unsat) with rich intermediate artifacts that can be mined for counterexamples, decompilation quality metrics, and bug root cause analysis.
