# D-Helix FastAPI Server

This folder contains the FastAPI REST API server for D-Helix binary verification.

## Files

- **api_server.py** - Main FastAPI server implementation
- **test_api_client.py** - Example client and test suite
- **requirements_api.txt** - Python dependencies for the API
- **API_DOCUMENTATION.md** - Complete API documentation

## Quick Start

### 1. Install Dependencies

```bash
cd /root/work/D-helix-fixed/fastapi_server
source /root/.virtualenvs/angr/bin/activate
pip install -r requirements_api.txt
```

### 2. Start the Server

```bash
python api_server.py
```

Server runs at: `http://0.0.0.0:10012`

### 3. Test the API

In a new terminal:

```bash
cd /root/work/D-helix-fixed/fastapi_server
source /root/.virtualenvs/angr/bin/activate
python test_api_client.py
```

## API Endpoints

- `GET /` - API information
- `GET /health` - Health check
- `POST /verify` - Verify binary vs decompiled code
- `GET /docs` - Interactive Swagger documentation

## Usage Example

```python
import requests

with open('my_binary', 'rb') as binary:
    response = requests.post(
        'http://localhost:10012/verify',
        files={
            'binary': ('binary', binary),
            'decompiled_code': ('code.c', decompiled_code)
        },
        data={'function_name': 'my_function'}
    )

result = response.json()
print(f"Result: {result['result']}")  # "sat" or "unsat"
```

## Documentation

See **API_DOCUMENTATION.md** for complete documentation including:
- Architecture details
- Request/response formats
- Result interpretation
- Troubleshooting guide
- Production deployment considerations

## Requirements

Requires D-Helix environment to be set up (see main README.md in parent directory).
