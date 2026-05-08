# Mobile Browser Testing

Mobile browsers require a secure context before exposing microphone capture. `http://localhost` is allowed for local desktop testing, but `http://<LAN IP>:5173` is not a secure context on a phone and can make `navigator.mediaDevices.getUserMedia` unavailable.

## Recommended Local Flow

1. Start the backend on the development machine:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```

2. Start the Vite frontend on the LAN:

   ```powershell
   cd frontend
   npm.cmd run dev -- --host 0.0.0.0
   ```

3. Open the frontend from the phone:

   ```text
   http://<computer-lan-ip>:5173
   ```

The Vite dev server proxies same-origin `/api` and `/ws` traffic to `http://localhost:8080`, so mobile testing does not require rewriting `VITE_API_BASE_URL` or `VITE_WS_BASE_URL`. If `frontend/.env.local` still contains `localhost` overrides, the frontend ignores those loopback overrides when the page is opened from a non-localhost device. Remove any non-loopback overrides, such as a stale LAN IP, when you want to validate the same-origin proxy path.

## Microphone Access

If the phone shows `Microphone recording is not supported in this browser`, the page is not running in a secure context. Use one of these options:

- Test through a real HTTPS staging domain.
- Use a trusted HTTPS tunnel to the local frontend.
- Configure Vite HTTPS with a certificate trusted by the phone, then access the HTTPS URL.
- For quick Android Chrome-only checks, temporarily allow the LAN origin through Chrome's insecure-origin development flag:

  1. Open Chrome on the phone and go to:

     ```text
     chrome://flags/#unsafely-treat-insecure-origin-as-secure
     ```

  2. Set the flag to `Enabled`.
  3. Add the exact frontend origin, including protocol and port:

     ```text
     http://<computer-lan-ip>:5173
     ```

  4. Relaunch Chrome when prompted.
  5. Reopen the frontend at the same origin and test live recording.

Do not treat browser flags as production validation. Production mobile use should be served through HTTPS and WebSocket traffic should use WSS.

## Production Expectations

Production deployments should expose the app through a browser-trusted certificate:

- Frontend: `https://app.example.com`
- API: same-origin `/api` or a trusted `https://api.example.com`
- Live WebSocket: same-origin `/ws/meeting` or a trusted `wss://api.example.com/ws/meeting`

Reverse proxies must forward WebSocket upgrade headers. Mobile background and lock-screen recording is still controlled by the operating system and browser; the app detects common interruptions but cannot guarantee capture while the page is suspended.
