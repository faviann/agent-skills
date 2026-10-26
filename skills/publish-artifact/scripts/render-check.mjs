import {existsSync, mkdtempSync, readFileSync} from "node:fs";
import {homedir, tmpdir} from "node:os";
import path from "node:path";
import {pathToFileURL} from "node:url";
import {parseArgs} from "node:util";

const ARTIFACT_ID = /^art_[0-9a-f-]{36}$/u;

function usage(message) {
  console.error(`render-check: ${message}`);
  console.error("usage: <artifact-id | url> [--token-file <path>] [--server <origin>] [--out <png>]");
  process.exit(2);
}

function findOnPath(candidate) {
  for (const directory of (process.env.PATH ?? "").split(path.delimiter)) {
    const file = candidate(directory);
    if (file !== null && existsSync(file)) return file;
  }
  return null;
}

// The script runs outside any package, so `import "playwright"` cannot resolve.
// npx puts the package's .bin on PATH; load the package beside it.
async function loadPlaywright() {
  const entry = findOnPath((directory) =>
    path.basename(directory) === ".bin" ? path.join(directory, "..", "playwright", "index.mjs") : null
  );
  if (entry === null) usage("playwright not found; run render-check.sh");
  return import(pathToFileURL(entry).href);
}

const IDLE_WAIT_MS = 5_000;

async function settleBriefly(page) {
  try {
    await page.waitForLoadState("networkidle", {timeout: IDLE_WAIT_MS});
  } catch (error) {
    if (error.name !== "TimeoutError") throw error;
  }
}

function fatal(error) {
  console.log(JSON.stringify({status: "error", message: String(error?.message ?? error)}));
  process.exit(3);
}

function hostConfiguration() {
  const configHome = path.isAbsolute(process.env.XDG_CONFIG_HOME ?? "")
    ? process.env.XDG_CONFIG_HOME
    : path.join(homedir(), ".config");
  const file = path.join(configHome, "faviann-skills", "artifact-server.json");
  if (!existsSync(file)) return {};
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    usage(`${file} is not valid JSON`);
  }
}

function readToken(file) {
  try {
    return readFileSync(file, "utf8").trim();
  } catch {
    usage(`cannot read token file ${file}`);
  }
}

function resolveTarget(target, server, token) {
  if (ARTIFACT_ID.test(target)) {
    if (token === null || !server) usage("an artifact id needs a server and token file from --server and --token-file, or from the host configuration");
    return {kind: "session", server, artifactId: target};
  }
  try {
    return {kind: "url", url: new URL(target).href};
  } catch {
    usage(`not an artifact id or URL: ${target}`);
  }
}

async function bootstrapUrl({server, artifactId}, token) {
  const response = await fetch(
    `${server}/api/v1/artifacts/${encodeURIComponent(artifactId)}/content-sessions`,
    {method: "POST", headers: {authorization: `Bearer ${token}`}},
  );
  if (response.status !== 201) {
    throw new Error(`content session for ${artifactId}: HTTP ${response.status} ${await response.text()}`);
  }
  return (await response.json()).bootstrapUrl;
}

const {values, positionals} = parseArgs({
  allowPositionals: true,
  options: {
    "token-file": {type: "string"},
    server: {type: "string"},
    out: {type: "string"},
  },
});
if (positionals.length !== 1) usage("expected exactly one artifact id or URL");

const host = hostConfiguration();
const tokenFile = values["token-file"] ?? host.tokenFile;
const token = tokenFile !== undefined && ARTIFACT_ID.test(positionals[0]) ? readToken(tokenFile) : null;
const server = (values.server ?? host.server ?? "").replace(/\/+$/u, "");
const target = resolveTarget(positionals[0], server, token);
const screenshot = path.resolve(
  values.out ?? path.join(mkdtempSync(path.join(tmpdir(), "artifact-render-")), "render.png"),
);
const {chromium} = await loadPlaywright();
const browser = await chromium.launch({
  executablePath: findOnPath((directory) => path.join(directory, "chromium")) ?? undefined,
}).catch(fatal);
const report = {url: null, status: null, consoleErrors: [], pageErrors: [], failedRequests: [], screenshot};
let failure = null;
try {
  const context = await browser.newContext();
  let startUrl = target.url;
  if (target.kind === "session") {
    // The exchange sets the content-session cookie in the context's jar, so the
    // page then loads the artifact itself instead of the bootstrap redirect page.
    const bootstrap = new URL(await bootstrapUrl(target, token));
    const exchange = await context.request.get(bootstrap.href);
    if (!exchange.ok()) throw new Error(`content session exchange: HTTP ${exchange.status()}`);
    bootstrap.searchParams.delete("__artifact_bootstrap");
    startUrl = bootstrap.href;
  }
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    // Chromium requests /favicon.ico on its own, and most artifacts ship none.
    if (new URL(message.location().url || "about:blank").pathname === "/favicon.ico") return;
    report.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => report.pageErrors.push(String(error)));
  page.on("requestfailed", (request) => {
    report.failedRequests.push({url: request.url(), error: request.failure()?.errorText ?? "failed"});
  });
  page.on("response", (response) => {
    if (response.status() >= 400) report.failedRequests.push({url: response.url(), status: response.status()});
  });
  const response = await page.goto(startUrl, {waitUntil: "load", timeout: 60_000});
  await settleBriefly(page);
  report.status = response?.status() ?? null;
  report.url = page.url();
  await page.screenshot({path: screenshot, fullPage: true});
} catch (error) {
  failure = error;
} finally {
  await browser.close();
}
if (failure !== null) fatal(failure);

console.log(JSON.stringify(report, null, 2));
const ok = report.status !== null && report.status >= 200 && report.status < 300 &&
  report.consoleErrors.length === 0 && report.pageErrors.length === 0;
process.exit(ok ? 0 : 1);
