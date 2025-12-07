# Cursor Project Instructions — TTB Label Verifier

## Architecture

- Frontend:
  - React + TypeScript SPA built with **Vite**.
  - **No Next.js, no React Server Components (RSC), no server-side React, no Flight protocol**.
  - Do not introduce SSR frameworks or RSC usage.
- Backend:
  - Python **FastAPI** app in `backend/app`.
  - Stateless API; each `/api/verify` call is independent.
- Communication:
  - Frontend calls backend via HTTP (`/api/*`) using `fetch` with `FormData` for uploads and JSON for responses.

## Security Constraints (React2Shell & general)

- The project must **avoid the React Server Components ecosystem** entirely to sidestep CVE-2025-55182 (“React2Shell”).
- Do not add code that:
  - Uses RSC, Flight protocol, or server-side rendering of React.
  - Introduces `eval`, `new Function`, or dynamic script injection.
  - Uses `dangerouslySetInnerHTML` to render server-provided data.
- Frontend:
  - Use standard React components rendered on the client only.
  - Sanitize or escape any user-provided strings if they ever need to be rendered as HTML (prefer plain text).
- Backend:
  - Accept only expected fields and file types on `/api/verify`.
  - Limit image size, reject obviously invalid uploads.
  - Treat OCR/LLM outputs as plain data; never execute them as code.
- Deployment:
  - Backend and frontend should be deployable separately (e.g., backend on Render/Fly.io, frontend as static build).
  - Assume HTTPS in production.

## Domain Logic

- Implement a pluggable `LabelAnalysisEngine`:
  - `ocr_local` (dummy or real OCR) and later a `multimodal_llm` implementation.
- `/api/verify` should:
  - Accept `multipart/form-data` with form fields and `image`.
  - Call the label engine.
  - Run normalization + comparison logic.
  - Return a structured `VerifyResult` object (`status` + per-field `checks`).

## DX

- Keep the code easy to run:
  - `uvicorn app.main:app --reload` for backend.
  - `npm run dev` for frontend.
- Keep types in sync between Python schemas and frontend TypeScript types.
- Prioritize a working end-to-end flow before adding advanced features.

## Python Dependencies & Virtual Environment

- **ALWAYS use the virtual environment** for installing Python dependencies:
  - The project has a virtual environment located at `backend/venv/`.
  - **NEVER install dependencies globally** (e.g., `pip install ...` without activating venv).
  - To install dependencies:
    1. Activate the virtual environment:
       - Windows: `backend\venv\Scripts\activate`
       - Linux/Mac: `source backend/venv/bin/activate`
    2. Then install: `pip install -r backend/requirements.txt`
  - When running tests or scripts, ensure the venv is activated or use the venv's Python directly:
     - `backend\venv\Scripts\python.exe -m pytest ...` (Windows)
     - `backend/venv/bin/python -m pytest ...` (Linux/Mac)
  - If you need to add a new dependency:
    1. Activate venv
    2. Install it: `pip install <package>`
    3. Update `backend/requirements.txt`: `pip freeze > backend/requirements.txt`