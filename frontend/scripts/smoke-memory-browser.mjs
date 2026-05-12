import { spawn } from 'node:child_process';
import { Buffer } from 'node:buffer';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const defaultScreenshotPath = path.join(rootDir, 'local-notes', 'screenshots', 'memory-workspace-smoke.png');
const defaultReportPath = path.join(rootDir, 'local-notes', 'memory-browser-smoke-report.json');

const frontendUrl = process.env.SMA_FRONTEND_URL || process.env.FRONTEND_URL || 'http://127.0.0.1:5174';
const screenshotPath = process.env.SMA_BROWSER_SCREENSHOT || defaultScreenshotPath;
const reportPath = process.env.SMA_BROWSER_REPORT || defaultReportPath;
const headless = !['0', 'false', 'no'].includes(String(process.env.SMA_BROWSER_HEADLESS || '1').toLowerCase());

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function pathExists(value) {
  if (!value) {
    return false;
  }
  try {
    await fs.access(value);
    return true;
  } catch {
    return false;
  }
}

async function findBrowserExecutable() {
  const candidates = [
    process.env.SMA_BROWSER_PATH,
    process.env.BROWSER_PATH,
    process.env.EDGE_PATH,
    process.env.CHROME_PATH,
    process.platform === 'win32' && process.env.PROGRAMFILES
      ? path.join(process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe')
      : '',
    process.platform === 'win32' && process.env['PROGRAMFILES(X86)']
      ? path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe')
      : '',
    process.platform === 'win32' && process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, 'Microsoft', 'Edge', 'Application', 'msedge.exe')
      : '',
    process.platform === 'win32' && process.env.PROGRAMFILES
      ? path.join(process.env.PROGRAMFILES, 'Google', 'Chrome', 'Application', 'chrome.exe')
      : '',
    process.platform === 'win32' && process.env['PROGRAMFILES(X86)']
      ? path.join(process.env['PROGRAMFILES(X86)'], 'Google', 'Chrome', 'Application', 'chrome.exe')
      : '',
    process.platform === 'win32' && process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe')
      : '',
    process.platform === 'darwin' ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : '',
    process.platform === 'darwin' ? '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge' : '',
    process.platform === 'linux' ? '/usr/bin/google-chrome' : '',
    process.platform === 'linux' ? '/usr/bin/google-chrome-stable' : '',
    process.platform === 'linux' ? '/usr/bin/microsoft-edge' : '',
    process.platform === 'linux' ? '/usr/bin/chromium' : '',
    process.platform === 'linux' ? '/usr/bin/chromium-browser' : '',
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (await pathExists(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    'Could not find Edge or Chrome. Set SMA_BROWSER_PATH to msedge.exe/chrome.exe and rerun npm run smoke:memory-browser.'
  );
}

async function findFreePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(() => {
        if (typeof address === 'object' && address) {
          resolve(address.port);
          return;
        }
        reject(new Error('Failed to reserve a local browser debugging port.'));
      });
    });
  });
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed ${response.status}: ${url}`);
  }
  return await response.json();
}

async function waitForDebugEndpoint(port) {
  const url = `http://127.0.0.1:${port}/json/version`;
  const startedAt = Date.now();
  let lastError;
  while (Date.now() - startedAt < 15000) {
    try {
      return await fetchJson(url);
    } catch (error) {
      lastError = error;
      await wait(250);
    }
  }
  throw new Error(`Browser debugging endpoint did not start: ${lastError?.message || 'timeout'}`);
}

async function createTarget(port, url) {
  const target = await fetchJson(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, {
    method: 'PUT',
  });
  if (!target.webSocketDebuggerUrl) {
    throw new Error('Browser target did not expose a WebSocket debugger URL.');
  }
  return target;
}

class CdpClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.events = new Map();
    this.consoleMessages = [];
    this.pageErrors = [];
    this.failedRequests = [];

    this.ws.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data);
      if (payload.id && this.pending.has(payload.id)) {
        const { resolve, reject } = this.pending.get(payload.id);
        this.pending.delete(payload.id);
        if (payload.error) {
          reject(new Error(`${payload.error.message}: ${payload.error.data || ''}`.trim()));
          return;
        }
        resolve(payload.result || {});
        return;
      }
      this.handleEvent(payload);
    });
  }

  async open() {
    if (this.ws.readyState === WebSocket.OPEN) {
      return;
    }
    await new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true });
      this.ws.addEventListener('error', () => reject(new Error('Failed to connect to browser debugger.')), { once: true });
    });
  }

  close() {
    if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
      this.ws.close();
    }
  }

  handleEvent(payload) {
    if (payload.method === 'Runtime.consoleAPICalled') {
      this.consoleMessages.push({
        type: payload.params.type,
        text: payload.params.args?.map((arg) => arg.value || arg.description || '').join(' '),
      });
    }
    if (payload.method === 'Runtime.exceptionThrown') {
      this.pageErrors.push(payload.params.exceptionDetails?.text || payload.params.exceptionDetails?.exception?.description || 'Runtime exception');
    }
    if (payload.method === 'Log.entryAdded') {
      const entry = payload.params.entry;
      if (entry.level === 'error') {
        this.pageErrors.push(entry.text);
      }
    }
    if (payload.method === 'Network.loadingFailed') {
      this.failedRequests.push(payload.params);
    }
    const listeners = this.events.get(payload.method);
    if (listeners) {
      for (const listener of listeners) {
        listener(payload.params || {});
      }
    }
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`Timed out waiting for ${method}.`));
        }
      }, 15000);
    });
  }

  once(method) {
    return new Promise((resolve) => {
      const listener = (params) => {
        const listeners = this.events.get(method) || [];
        this.events.set(method, listeners.filter((item) => item !== listener));
        resolve(params);
      };
      const listeners = this.events.get(method) || [];
      listeners.push(listener);
      this.events.set(method, listeners);
    });
  }
}

async function evaluate(client, expression, options = {}) {
  const result = await client.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
    ...options,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || 'Runtime evaluation failed.');
  }
  return result.result?.value;
}

async function waitForText(client, text, timeoutMs = 15000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const bodyText = await evaluate(client, 'document.body?.innerText || ""');
    if (bodyText.includes(text)) {
      return bodyText;
    }
    await wait(300);
  }
  throw new Error(`Timed out waiting for visible text: ${text}`);
}

async function clickButtonByText(client, text) {
  const clicked = await evaluate(
    client,
    `(() => {
      const button = Array.from(document.querySelectorAll('button')).find((item) => item.textContent.trim() === ${JSON.stringify(text)});
      if (!button) return false;
      button.click();
      return true;
    })()`
  );
  if (!clicked) {
    throw new Error(`Could not find button with text: ${text}`);
  }
}

async function selectFirstNonAllCollection(client) {
  return await evaluate(
    client,
    `(() => {
      const select = document.querySelector('select[aria-label="Memory collection"]');
      if (!select) return { found: false };
      const option = Array.from(select.options).find((item) => item.value !== 'all');
      if (!option) return { found: true, changed: false, value: select.value, label: select.selectedOptions[0]?.textContent || '' };
      select.value = option.value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      return { found: true, changed: true, value: option.value, label: option.textContent || '' };
    })()`
  );
}

async function assertVisibleText(client, requiredText) {
  const bodyText = await evaluate(client, 'document.body?.innerText || ""');
  const missing = requiredText.filter((item) => !bodyText.includes(item));
  if (missing.length) {
    throw new Error(`Missing expected Memory workspace text: ${missing.join(', ')}`);
  }
  return bodyText;
}

async function runSmoke(client) {
  const loadEvent = client.once('Page.loadEventFired');
  await client.send('Page.navigate', { url: frontendUrl });
  await loadEvent;
  await waitForText(client, 'Smart Meeting Assistant');

  await clickButtonByText(client, 'Memory');
  await waitForText(client, 'Project Memory');

  await assertVisibleText(client, [
    'Project Memory',
    'Next Meeting Brief',
    'Action Item Center',
    'Decision Log',
    'Risk Tracker',
    'Open Questions',
    'Meetings',
    'Pending',
    'Completed',
    'Decisions',
    'Risks',
    'Questions',
  ]);

  const collectionSwitch = await selectFirstNonAllCollection(client);
  if (collectionSwitch.changed) {
    await wait(1000);
    await waitForText(client, 'Project Memory');
  }

  const summary = await evaluate(
    client,
    `(() => {
      const text = document.body.innerText;
      return {
        title: document.title,
        url: location.href,
        selectedCollection: document.querySelector('select[aria-label="Memory collection"]')?.selectedOptions[0]?.textContent || '',
        hasProjectMemory: text.includes('Project Memory'),
        hasNextMeetingBrief: text.includes('Next Meeting Brief'),
        hasActionItemCenter: text.includes('Action Item Center'),
        hasDecisionLog: text.includes('Decision Log'),
        hasRiskTracker: text.includes('Risk Tracker'),
        hasOpenQuestions: text.includes('Open Questions'),
        textHash: ${JSON.stringify('sha256 unavailable in page')},
      };
    })()`
  );
  const bodyText = await evaluate(client, 'document.body?.innerText || ""');
  summary.textHash = createHash('sha256').update(bodyText).digest('hex');
  summary.collectionSwitch = collectionSwitch;
  return summary;
}

async function main() {
  const browserPath = await findBrowserExecutable();
  const port = await findFreePort();
  const profileDir = await fs.mkdtemp(path.join(os.tmpdir(), 'sma-browser-smoke-'));
  const args = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-features=Translate,AutofillServerCommunication',
    '--window-size=1440,1000',
    'about:blank',
  ];
  if (headless) {
    args.unshift('--headless=new');
  }

  const browser = spawn(browserPath, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: headless,
  });

  let client;
  try {
    browser.stderr.on('data', (chunk) => {
      const text = chunk.toString();
      if (/error|failed/i.test(text) && !/DevTools listening/i.test(text)) {
        process.stderr.write(text);
      }
    });

    await waitForDebugEndpoint(port);
    const target = await createTarget(port, frontendUrl);
    client = new CdpClient(target.webSocketDebuggerUrl);
    await client.open();
    await client.send('Page.enable');
    await client.send('Runtime.enable');
    await client.send('Log.enable');
    await client.send('Network.enable');
    await client.send('Emulation.setDeviceMetricsOverride', {
      width: 1440,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: false,
    });

    const smoke = await runSmoke(client);
    const screenshot = await client.send('Page.captureScreenshot', {
      format: 'png',
      fromSurface: true,
      captureBeyondViewport: false,
    });

    await fs.mkdir(path.dirname(screenshotPath), { recursive: true });
    await fs.writeFile(screenshotPath, Buffer.from(screenshot.data, 'base64'));

    const report = {
      ok: true,
      timestamp: new Date().toISOString(),
      frontendUrl,
      browserPath,
      headless,
      screenshotPath,
      smoke,
      consoleMessages: client.consoleMessages,
      pageErrors: client.pageErrors,
      failedRequests: client.failedRequests.map((item) => ({
        requestId: item.requestId,
        errorText: item.errorText,
        type: item.type,
      })),
    };
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2), 'utf8');

    console.log(`Memory browser smoke passed.`);
    if (client.pageErrors.length || client.failedRequests.length) {
      console.log(`Browser warnings were recorded in the report.`);
    }
    console.log(`Screenshot: ${screenshotPath}`);
    console.log(`Report: ${reportPath}`);
  } finally {
    client?.close();
    browser.kill();
    await wait(500);
    await fs.rm(profileDir, { recursive: true, force: true });
  }
}

main().catch(async (error) => {
  const report = {
    ok: false,
    timestamp: new Date().toISOString(),
    frontendUrl,
    error: error instanceof Error ? error.message : String(error),
  };
  await fs.mkdir(path.dirname(reportPath), { recursive: true });
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2), 'utf8');
  console.error(report.error);
  process.exitCode = 1;
});
