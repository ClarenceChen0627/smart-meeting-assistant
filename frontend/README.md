
# Smart Meeting Assistant - Frontend

This is the React 18, Tailwind CSS, and Radix UI powered frontend interface for the Smart Meeting Assistant. Everything is bundled via Vite. The same frontend can also run inside the Windows-first Electron desktop shell in `electron/main.cjs`.

## Running the code

Make sure you have Node 18+ installed.

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Start the development server:**
   ```bash
   npm run dev
   ```

3. **Build for production:**
   ```bash
   npm run build
   ```

4. **Production Preview:**
   ```bash
   npm run preview
   ```

## Electron desktop client

The Electron app wraps this Vite frontend only. It does not bundle the Python/FastAPI backend, so start the backend separately before recording.

Configure the backend WebSocket endpoint in `.env.local` when needed:

```bash
VITE_WS_BASE_URL=ws://localhost:8080
```

Run the Electron development shell:

```bash
npm run dev:electron
```

Build the Windows portable executable:

```bash
npm run electron:pack
```

The portable build is written to `release/`.
  
