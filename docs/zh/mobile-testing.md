# 移动端浏览器测试

移动端浏览器要求页面处于安全上下文后才会开放麦克风采集。桌面本机测试的 `http://localhost` 可以使用麦克风，但手机访问 `http://<局域网 IP>:5173` 通常不算安全上下文，可能导致 `navigator.mediaDevices.getUserMedia` 不可用。

## 推荐本地流程

1. 在开发机器上启动后端：

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```

2. 在局域网内启动 Vite 前端：

   ```powershell
   cd frontend
   npm.cmd run dev -- --host 0.0.0.0
   ```

3. 手机打开前端：

   ```text
   http://<电脑局域网 IP>:5173
   ```

Vite dev server 会把同源 `/api` 和 `/ws` 代理到 `http://localhost:8080`，所以手机测试不需要反复改 `VITE_API_BASE_URL` 或 `VITE_WS_BASE_URL`。如果 `frontend/.env.local` 仍然写着 `localhost`，当前前端在非 localhost 设备访问时会忽略这些 loopback override。如果要验证同源代理路径，请移除旧的非 loopback override，例如之前手动写入的局域网 IP。

## 麦克风权限

如果手机显示 `Microphone recording is not supported in this browser`，说明页面不是安全上下文。可以使用以下方式之一：

- 通过真实 HTTPS staging 域名测试。
- 使用受信任的 HTTPS tunnel 指向本地前端。
- 给 Vite HTTPS 配置手机信任的证书，然后访问 HTTPS 地址。
- Android Chrome 快速验证时，可以临时把局域网 origin 加入 insecure-origin 开发 flag：

  1. 在手机 Chrome 打开：

     ```text
     chrome://flags/#unsafely-treat-insecure-origin-as-secure
     ```

  2. 将该 flag 设置为 `Enabled`。
  3. 填入完整前端 origin，包括协议和端口：

     ```text
     http://<电脑局域网 IP>:5173
     ```

  4. 按提示 relaunch Chrome。
  5. 重新打开同一个前端地址并测试实时录音。

浏览器 flag 只能用于临时开发验证，不应作为生产验收。生产移动端使用应走 HTTPS，WebSocket 应走 WSS。

## 生产预期

生产部署应使用浏览器信任的证书：

- 前端：`https://app.example.com`
- API：同源 `/api` 或受信任的 `https://api.example.com`
- 实时 WebSocket：同源 `/ws/meeting` 或受信任的 `wss://api.example.com/ws/meeting`

反向代理必须转发 WebSocket upgrade headers。移动端后台和锁屏录音仍由操作系统与浏览器控制；应用会检测常见中断，但不能保证页面挂起后继续采集。
