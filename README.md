# D-Helix: Binary Verification System

D-Helix is a formal verification tool that checks whether decompiled source code is semantically equivalent to an original binary. It uses symbolic execution and SMT solving to prove equivalence or find counterexamples (bugs).

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│  Original       │     │  Decompiled     │
│  Binary         │     │  Source Code    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  ANGR           │     │  Clang-16       │
│  (VEX IR)       │     │  (LLVM BC)      │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │                       ▼
         │              ┌─────────────────┐
         │              │  KLEE/PROMPT    │
         │              │  (Symbolic Exec)│
         │              └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  IR Formula     │     │  IR Formula     │
│  (Binary)       │     │  (Decompiled)   │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
            ┌─────────────────┐
            │  Z3 SMT Solver  │
            │  Equivalence?   │
            └────────┬────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
    ┌─────────┐            ┌─────────┐
    │  UNSAT  │            │   SAT   │
    │ (Equal) │            │  (Bug!) │
    └─────────┘            └─────────┘
```

## Quick Start (Docker)

### Build and Run

```bash
# Build the Docker image
docker build -t d-helix .

# Run the API server
docker run -p 10012:10012 d-helix

# Server available at http://localhost:10012
# API docs at http://localhost:10012/docs
```

### Using Docker Compose

```bash
docker-compose up -d
```

## API Usage

### Verify a Function

```bash
curl -X POST http://localhost:10012/verify \
  -F "binary=@/path/to/binary" \
  -F "decompiled_code=@/path/to/decompiled.c" \
  -F "function_name=add" \
  -F "is_cpp=false"
```

### Python Example

```python
import requests

# Prepare files
with open('binary', 'rb') as binary_file:
    binary_data = binary_file.read()

decompiled_code = """
int add(int a, int b) {
    return a + b;
}
"""

# Call API
response = requests.post(
    'http://localhost:10012/verify',
    files={
        'binary': ('binary', binary_data, 'application/octet-stream'),
        'decompiled_code': ('add.c', decompiled_code, 'text/plain')
    },
    data={
        'function_name': 'add',
        'is_cpp': 'false'
    }
)

result = response.json()
print(f"Status: {result['status']}")
print(f"Result: {result['result']}")  # 'unsat' = equivalent, 'sat' = bug found

if result['result'] == 'sat':
    print(f"Counterexample: {result.get('counterexample')}")
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/verify` | POST | Verify binary against decompiled code |
| `/health` | GET | Health check |
| `/` | GET | API info and available endpoints |
| `/docs` | GET | Interactive API documentation (Swagger) |

### POST /verify Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `binary` | file | Yes | Binary executable to verify |
| `decompiled_code` | file | Yes | Decompiled C/C++ source code |
| `function_name` | string | Yes | Name of function to verify |
| `is_cpp` | boolean | No | Set to `true` for C++ code (default: false) |

### Response Format

```json
{
  "request_id": "uuid",
  "status": "success",
  "result": "unsat",
  "z3_formula": "...",
  "counterexample": null,
  "execution_time": 1.23
}
```

- `result: "unsat"` → Binary and decompiled code are **equivalent**
- `result: "sat"` → **Bug found!** Counterexample shows differing inputs

## Supported Languages

| Language | Support | Notes |
|----------|---------|-------|
| C | ✅ Full | All standard C functions |
| C++ | ✅ Full | Use `extern "C"` or set `is_cpp=true` |

### C++ Example

```cpp
// With extern "C" (recommended)
extern "C" int add(int a, int b) {
    return a + b;
}

// Without extern "C" - set is_cpp=true
int add(int a, int b) {
    return a + b;
}
```

## Running Tests

```bash
# Inside the container or with environment set up
cd fastapi_server

# Run comprehensive test suite (29 tests)
python test_comprehensive.py

# Run specific test category
python test_comprehensive.py --test c_add
python test_comprehensive.py --test cpp_
python test_comprehensive.py --test klee_
python test_comprehensive.py --test error_
```

### Test Categories

| Category | Tests | Description |
|----------|-------|-------------|
| `health_*` | 2 | Server health checks |
| `c_*` | 12 | C function verification |
| `cpp_*` | 3 | C++ function verification |
| `error_*` | 3 | Error handling (invalid input) |
| `klee_*` | 6 | KLEE edge cases and resilience |
| `consistency_*` | 2 | Repeated request consistency |
| `stress_*` | 1 | Sequential stress testing |

## Scaling for Production

### Multiple Workers

```bash
# Run with 12 Uvicorn workers
docker run -d   --name dhelix   -p 10012:10012   dhelix-server   /root/.virtualenvs/angr/bin/python -m uvicorn api_server:app --host 0.0.0.0 --port 10012 --workers 12
```

### Resource Recommendations

| CPUs | RAM | Recommended Workers |
|------|-----|---------------------|
| 4 | 16GB | 2-3 |
| 12 | 64GB | 6-8 |
| 24 | 256GB | 12-16 |

## Known Limitations

1. **KLEE Limitations**: Some complex code patterns may cause KLEE to fail:
   - Function pointers / indirect calls
   - Complex loops with symbolic bounds
   - Heavy type casting (bitcast in LLVM IR)
   
   D-Helix handles these gracefully and returns descriptive errors.

2. **Symbolic Execution Timeouts**: Very complex functions may timeout during symbolic execution.

3. **Shift Operations**: Bit shift operations with symbolic amounts may return `sat` due to symbolic execution limitations (known issue).

## File Structure

```
D-helix-fixed/
├── Dockerfile              # Docker build configuration
├── docker-compose.yml      # Docker Compose configuration
├── README.md               # This file
├── README_SETUP_GUIDE.md   # Manual setup instructions
├── D-helix/
│   ├── D_helix_angr/       # ANGR-based analysis modules
│   │   ├── analyze_angr.py # Binary analysis with ANGR
│   │   ├── analyze_results.py # KLEE output processing
│   │   ├── convert.py      # IR to Z3 conversion
│   │   └── muqi.py         # Custom ANGR analysis
│   └── *.patch             # Patches for ANGR/KLEE/PROMPT
└── fastapi_server/
    ├── api_server.py       # FastAPI REST server
    ├── requirements_api.txt # Python dependencies
    ├── test_comprehensive.py # Full test suite (29 tests)
    ├── test_api_client.py  # Basic API client tests
    └── API_DOCUMENTATION.md # Detailed API docs
```

## Troubleshooting

### Server Returns 500 Error

Check the server logs for specific error messages:
- `"KLEE output processing failed"` - KLEE couldn't handle the code (normal for complex functions)
- `"Z3 solver execution failed"` - Z3 couldn't solve the formula (may need more time/memory)

### Function Not Found

Ensure the `function_name` parameter matches the function name in both:
1. The compiled binary (use `nm binary | grep function_name`)
2. The decompiled source code

### C++ Name Mangling

For C++ code without `extern "C"`:
- Set `is_cpp=true` in the request
- D-Helix will attempt to detect and handle mangled names

## Contributing

See the detailed setup guide in [README_SETUP_GUIDE.md](README_SETUP_GUIDE.md) for manual environment configuration.

## License

See [D-helix/LICENSE](D-helix/LICENSE)
