# TTB Label Verifier - Backend

Backend API for verifying TTB labels against regulations.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the server:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

- `GET /` - API information
- `GET /health` - Health check
- `POST /api/v1/verify` - Verify a label

