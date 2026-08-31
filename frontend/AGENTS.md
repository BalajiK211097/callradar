# frontend

React 19 + Vite 8 + Tailwind CSS v4 SPA. Package manager is **pnpm**.

## Development Server

```bash
cd frontend
pnpm install
pnpm dev    # http://localhost:5173
```

## Project Structure

- `src/main.tsx` — React entrypoint; imports `src/index.css` and mounts `src/App.tsx`
- `src/App.tsx` — Root component with auth gate
- `src/index.css` — Global CSS; Tailwind v4 import; `.card` and `.font-mono` utility classes
- `src/routes.tsx` — React Router v8 route definitions
- `src/pages/` — Page components (Overview, AllCalls, CallDetail, AgentsList, AgentDetail, CustomersList, CustomerDetail, Trends, Login)
- `src/components/` — Shared components (Layout, Badges)
- `src/lib/api.ts` — Typed fetch client for the FastAPI backend at `http://localhost:8000`
- `src/lib/format.ts` — Formatting helpers (fmtTime, fmtDuration, fmtRate, initials)
- `src/context/AuthContext.tsx` — Auth context (demo login)

## Styling

Tailwind CSS v4 via `@tailwindcss/vite` plugin. No tailwind config file needed. Custom classes in `index.css`:
- `.card` — white card with border, radius, and subtle shadow
- `.font-mono` — JetBrains Mono

Use Tailwind utility classes in JSX. Inline `style={{}}` for dynamic values (colors from data).

## Code quality

- Double quotes for strings with apostrophes.
- Ensure JSX tags are closed and braces are balanced.
- Export components as default exports.
