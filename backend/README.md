# BugPilot backend

## Windows setup
```bat
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.api.main:app --reload
```

## Ubuntu/Linux setup
```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.api.main:app --reload
```

Open API documentation at http://127.0.0.1:8000/docs. The bundled local demo login is `bugpilot.admin` / `BugPilotDemo!2026`. Change it before sharing/deployment and replace the development JWT secret in `.env`.

## Database and retrieval
The database is `backend/bugpilot.db`; the Chroma persistent store is `backend/vector_db/`. The enterprise ticket FTS5 index is created/rebuilt by the database initialization code. If the Chroma collection is empty or needs rebuilding, run `python -m app.vectorstore.index_tickets` from the backend directory after dependencies and the sentence-transformer model are available.

## AI provider
The default LLM provider is Ollama (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`). If Ollama is unavailable, the API deliberately returns a low-confidence local fallback instead of failing the whole request. If you have a Hugging Face Inference Providers token, set `LLM_PROVIDER=huggingface` and fill `HF_TOKEN` in `.env`; `HF_MODEL` and `HF_API_URL` are configurable. Never commit a real token. Ticket, history, authentication, and analytics functionality does not require an LLM provider.

## Security and data safety
- Back up `bugpilot.db` before manual migrations or seed operations.
- Do not run seed scripts against a populated database unless you intend to change the sample data.
- Do not commit `.env` or real credentials to source control.
- Role-based visibility is enforced in the backend; UI role checks are not the security boundary.
