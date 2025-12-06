# TTB Label Verifier - Backend

Backend API for verifying TTB labels against regulations.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export ENGINE_MODE=local  # or "multimodal_llm"
export GEMINI_API_KEY=your_key_here  # if using multimodal_llm
export OPENAI_API_KEY=your_key_here  # if using multimodal_llm
```

3. Run the server:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

- `GET /` - API information
- `GET /health` - Health check
- `POST /api/v1/verify` - Verify a label

