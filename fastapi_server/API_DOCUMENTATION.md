# D-Helix FastAPI Server Documentation

## Overview

The D-Helix FastAPI server provides a REST API for verifying semantic equivalence between binary executables and their decompiled source code using symbolic execution.

## Architecture

The API wraps the D-Helix verification pipeline (stages 2-7):

```
Binary + Decompiled Code  →  API Server  →  Z3 Formula + sat/unsat + Counterexamples
                                  ↓
                    ┌─────────────────────────┐
                    │  Stage 3: Compilation   │
                    │  LLVM clang-3.8         │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │  Stage 4a: KLEE         │
                    │  Symbolic Execution     │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │  Stage 4b: Angr         │
                    │  Symbolic Execution     │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │  Stage 5: IR Processing │
                    │  analyze_angr.py        │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │  Stage 6: Z3 Generation │
                    │  convert.py:ir_to_z3()  │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │  Stage 7: Z3 Solver     │
                    │  Result + Counterexample│
                    └─────────────────────────┘
```

## Installation

### Prerequisites

Ensure D-Helix environment is set up (see main README.md steps 1-11):
- Python 3.8 with angr virtualenv
- LLVM 3.8
- KLEE/PROMPT
- Z3 4.9.1
- Angr (patched version)

### Install API Dependencies

```bash
cd /root/work/D-helix-fixed/D-helix/D_helix_angr
source /root/.virtualenvs/angr/bin/activate
pip install -r requirements_api.txt
```

## Running the Server

### Start Server

```bash
cd /root/work/D-helix-fixed/D-helix/D_helix_angr
source /root/.virtualenvs/angr/bin/activate
python api_server.py
```

Server will start on `http://0.0.0.0:8000`

### Production Deployment

For production with multiple workers:

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### 1. Health Check

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "service": "D-Helix Verification API",
  "version": "1.0.0"
}
```

### 2. Root Information

**Endpoint:** `GET /`

**Response:**
```json
{
  "service": "D-Helix Binary Verification API",
  "version": "1.0.0",
  "endpoints": {
    "/verify": "POST - Verify binary against decompiled code",
    "/health": "GET - Health check",
    "/docs": "GET - API documentation"
  }
}
```

### 3. Verify Decompilation

**Endpoint:** `POST /verify`

**Content-Type:** `multipart/form-data`

**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `binary` | File | Yes | Binary executable file (single function) |
| `decompiled_code` | File | Yes | Decompiled C source code |
| `function_name` | String | Yes | Name of function to verify |

**Example Request (Python):**

```python
import requests

with open('binary_file', 'rb') as binary, open('decompiled.c', 'r') as code:
    files = {
        'binary': ('binary', binary, 'application/octet-stream'),
        'decompiled_code': ('decompiled.c', code, 'text/plain')
    }
    data = {
        'function_name': 'my_function'
    }
    
    response = requests.post(
        'http://localhost:8000/verify',
        files=files,
        data=data,
        timeout=120
    )
    
    result = response.json()
```

**Example Request (cURL):**

```bash
curl -X POST http://localhost:8000/verify \
  -F "binary=@./test_binary" \
  -F "decompiled_code=@./decompiled.c" \
  -F "function_name=add"
```

**Response Schema:**

```json
{
  "request_id": "uuid-string",
  "status": "success|error",
  "z3_formula": "Z3 SMT-LIB formula content",
  "result": "sat|unsat",
  "counterexample": {
    "variable_name": "value",
    ...
  },
  "error_message": "error description (if status=error)"
}
```

**Response Fields:**

- `request_id`: Unique identifier for this verification request
- `status`: `"success"` or `"error"`
- `z3_formula`: Complete Z3 SMT-LIB formula used for verification
- `result`: 
  - `"unsat"`: Binary and decompiled code are semantically EQUIVALENT ✅
  - `"sat"`: Semantic DIFFERENCE detected (decompilation bug) ⚠️
- `counterexample`: If `result="sat"`, concrete input values that demonstrate the difference
- `error_message`: Error description if `status="error"`

## Result Interpretation

### ✅ Result: "unsat" (Expected)

```json
{
  "result": "unsat"
}
```

**Meaning:** No counterexample exists that proves inequality.
**Interpretation:** Binary and decompiled code are **semantically equivalent**.
**Action:** Decompilation is correct!

### ⚠️ Result: "sat" (Bug Detected)

```json
{
  "result": "sat",
  "counterexample": {
    "angr_arg0_42_64": "#x0000000000000005",
    "angr_arg1_43_64": "#x0000000000000003"
  }
}
```

**Meaning:** Found concrete inputs where binary ≠ decompiled code.
**Interpretation:** **Decompilation bug detected**.
**Action:** Review decompiled code - it doesn't match binary behavior.

## Usage Examples

### Example 1: Verify Correct Decompilation

```python
# test_correct.py
import requests

binary_path = "./my_binary"
decompiled_code = """
int add(int a, int b) {
    return a + b;
}
"""

with open(binary_path, 'rb') as f:
    response = requests.post(
        'http://localhost:8000/verify',
        files={
            'binary': ('binary', f),
            'decompiled_code': ('code.c', decompiled_code)
        },
        data={'function_name': 'add'}
    )

result = response.json()
print(f"Result: {result['result']}")  # Expected: "unsat" (correct)
```

### Example 2: Detect Buggy Decompilation

```python
# test_buggy.py
buggy_code = """
int add(int a, int b) {
    return a * b;  // BUG: should be a + b
}
"""

with open('./my_binary', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/verify',
        files={
            'binary': ('binary', f),
            'decompiled_code': ('code.c', buggy_code)
        },
        data={'function_name': 'add'}
    )

result = response.json()
print(f"Result: {result['result']}")  # Expected: "sat" (bug detected!)
if result['counterexample']:
    print(f"Inputs that expose bug: {result['counterexample']}")
```

## Testing

Run the included test client:

```bash
cd /root/work/D-helix-fixed/D-helix/D_helix_angr
source /root/.virtualenvs/angr/bin/activate
python test_api_client.py
```

This will:
1. Test correct decompilation of `add()` function
2. Test correct decompilation of `subtract()` function
3. Test buggy decompilation detection

## Performance Considerations

### Timeouts

- KLEE execution: 30 seconds
- Angr execution: 60 seconds  
- Z3 solver: 30 seconds
- Total request: ~120 seconds

### Concurrency

- Default: 4 concurrent workers
- Each verification is CPU-intensive
- Adjust `MAX_WORKERS` in `api_server.py` based on server capacity

### Resource Usage

Per request:
- Memory: ~2-4 GB (Angr + KLEE + Z3)
- CPU: 100% of 1-2 cores
- Disk: ~100 MB temp files (auto-cleaned)

## Troubleshooting

### Error: "Failed to compile decompiled code"

**Cause:** Decompiled C code has syntax errors or missing includes.

**Solution:** Ensure decompiled code is valid C and compilable with clang-3.8.

### Error: "Angr symbolic execution failed"

**Cause:** Function not found in binary or CFG generation failed.

**Solution:** 
- Verify function name is correct
- Check binary has debug symbols
- Try FUN_<hex_address> format for Ghidra-decompiled functions

### Error: "KLEE execution incomplete"

**Cause:** KLEE timeout or crash.

**Solution:** 
- Check decompiled code complexity
- Increase `TIMEOUT_KLEE` in api_server.py
- Review KLEE logs in temp directory

### Connection Refused

**Cause:** Server not running or firewall blocking.

**Solution:**
```bash
# Check server is running
curl http://localhost:8000/health

# Start server if needed
cd /root/work/D-helix-fixed/D-helix/D_helix_angr
source /root/.virtualenvs/angr/bin/activate
python api_server.py
```

## API Documentation (Swagger)

Interactive API documentation available at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

## Security Considerations

### Production Deployment

⚠️ **Warning:** This API executes arbitrary binaries and code. For production:

1. **Sandboxing:** Run in isolated container/VM
2. **Authentication:** Add API key/OAuth authentication
3. **Rate Limiting:** Prevent abuse
4. **Input Validation:** Verify binary/code format
5. **Resource Limits:** Set memory/CPU quotas
6. **Monitoring:** Log all requests and failures

Example with API key middleware:

```python
from fastapi.security import APIKeyHeader
from fastapi import Security, HTTPException

API_KEY = "your-secret-api-key"
api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

@app.post("/verify")
async def verify_binary(
    api_key: str = Security(verify_api_key),
    # ... rest of parameters
):
    # ... verification logic
```

## Architecture Details

### Pipeline Stages

1. **File Reception** (FastAPI)
   - Accept binary + decompiled code via multipart/form-data
   - Create temporary working directory
   - Save files to disk

2. **Compilation** (`compile_to_bitcode`)
   - Wrap decompiled C with headers
   - Compile to LLVM bitcode using clang-3.8

3. **KLEE Execution** (`run_klee_symbolic_execution`)
   - Generate PROMPT model file
   - Run KLEE with Z3 backend
   - Capture constraint logs

4. **Angr Execution** (`run_angr_symbolic_execution`)
   - Load binary with angr
   - Generate CFG
   - Run symbolic execution
   - Log basic blocks and constraints

5. **IR Processing** (`generate_z3_formula`)
   - Parse Angr logs (`analyze_angr.py`)
   - Parse KLEE logs (`analyze_results.py`)
   - Generate intermediate representations

6. **Z3 Generation** (`convert.ir_to_z3`)
   - Convert both IRs to Z3 SMT-LIB format
   - Generate equivalence formula
   - Write to .z3 file

7. **Verification** (`run_z3_solver`)
   - Execute Z3 solver
   - Parse sat/unsat result

8. **Counterexample Extraction** (if sat)
   - Re-run Z3 with `(get-model)`
   - Parse variable assignments

### File Organization

```
/tmp/dhelix_api/<request_id>/
├── binary              # Uploaded binary
├── decompiled.c        # Uploaded C code
├── decompiled.bc       # Compiled bitcode
├── model.txt           # PROMPT model
├── klee_log.txt        # KLEE stdout
├── klee_error.txt      # KLEE stderr
├── angr_log.txt        # Angr logs
├── angr_log_ir_*.txt   # Intermediate IR files
├── klee_log_cfg*.txt   # KLEE CFG files
├── klee_log_ir*.txt    # KLEE IR files
└── verification.z3     # Final Z3 formula
```

## Support

For issues or questions:
- Check D-Helix documentation: `/root/work/D-helix-fixed/D-helix/`
- Review logs in `/tmp/dhelix_api/`
- Enable debug logging: `logging.basicConfig(level=logging.DEBUG)`

## License

Same as D-Helix project license.
