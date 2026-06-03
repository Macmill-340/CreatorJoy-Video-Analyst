// In dev: VITE_API_URL is unset → falls back to '/api' → Vite proxy strips
//         the prefix and forwards to http://localhost:8000  (no change needed
//         to vite.config.js — the existing proxy already handles this).
//
// In prod (Render): set VITE_API_URL=https://your-backend.onrender.com in
//         the Static Site's environment variables. Calls go directly there
//         with no proxy involved.

export const API = import.meta.env.VITE_API_URL ?? '/api'