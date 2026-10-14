# BugPilot frontend

## Run
```bat
npm install
copy .env.example .env
npm run dev
```
Set `VITE_API_BASE_URL` in `.env` if your backend is hosted at a different URL. Vite reads frontend variables prefixed with `VITE_`.

This frontend uses the FastAPI endpoints in the sibling `backend` folder. Run the backend first at `http://127.0.0.1:8000`.
