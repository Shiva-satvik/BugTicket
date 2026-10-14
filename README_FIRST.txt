BUGPILOT — REPAIRED DEVELOPMENT BUNDLE
=====================================

This bundle contains the latest individually uploaded React/FastAPI source files, the SQLite sample database, the Chroma vector store, setup scripts, and a local demo administrator account.

RECOMMENDED ENVIRONMENT
- Windows 10/11 or Ubuntu
- Python 3.12 for backend compatibility
- Node.js 22.12+ and npm for the frontend
- Internet access for the first dependency install and (if needed) the sentence-transformer model download

FAST START — WINDOWS
1. Double-click RUN_BACKEND.bat and wait for the API to start.
2. Double-click RUN_FRONTEND.bat in a second terminal/window.
3. Open http://localhost:5173
4. API docs: http://127.0.0.1:8000/docs

FAST START — MANUAL WINDOWS COMMANDS
Backend terminal:
  cd backend
  py -3.12 -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  copy .env.example .env
  python -m uvicorn app.api.main:app --reload

Frontend terminal:
  cd bugpilot-frontend
  npm install
  copy .env.example .env
  npm run dev

LOCAL DEMO LOGIN
  Username: bugpilot.admin
  Password: BugPilotDemo!2026

This credential is only for local development. Change it before any shared or production deployment. The bundled DB is a sample/demo DB; keep a backup before making schema or seed changes.

AI / RAG NOTES
- The API and ticket-management screens can run without a local Ollama server; AI analysis will return an explicitly low-confidence rule-based fallback if the AI graph/provider fails.
- Full LLM analysis requires a working Ollama server and configured model, or a Hugging Face Inference Providers token: set LLM_PROVIDER=huggingface and HF_TOKEN in backend/.env. Never commit a real token.
- Semantic search requires the sentence-transformer model. The existing Chroma vector store is included. If you see an empty or stale collection, activate the backend environment and run:
    python -m app.vectorstore.index_tickets
- Do not rerun seed scripts on the bundled database unless you intentionally want to add/refresh sample data.

NOTES
- Frontend API base URL is configured in bugpilot-frontend/.env (VITE_API_BASE_URL=http://127.0.0.1:8000).
- Backend database path is backend/bugpilot.db.
- Change JWT_SECRET_KEY in backend/.env before deploying or sharing the app.
- This is a development bundle, not a production security audit.
