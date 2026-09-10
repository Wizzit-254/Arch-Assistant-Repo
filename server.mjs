// Arch Assistant — hardened download server (zero dependencies, Node >= 18).
//
// What it does:
//   - Serves the static site with strict security headers (HSTS, CSP, anti-clickjacking…).
//   - Protects the installer endpoints with proof-of-work challenges + single-use
//     signed tickets + per-IP rate limits, so dumb bots / scrapers / hotlinkers
//     can't leech the binaries. A real browser solves ~1s of SHA-256 work; a bot
//     farm pays that cost on every single download attempt.
//   - Never serves its own source, configs, or the raw installer directory.
//
// Run:  ARCH_SECRET=<long random> PORT=8080 node server.mjs
// Live: put Caddy (see Caddyfile) in front for automatic HTTPS, set TRUST_PROXY=1.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 8080);
const SECRET = process.env.ARCH_SECRET || crypto.randomBytes(32).toString('hex');
if (!process.env.ARCH_SECRET) {
  console.warn('[warn] ARCH_SECRET not set — using an ephemeral secret (all tickets reset on restart).');
}
const POW_DIFFICULTY = Math.max(1, Math.min(6, parseInt(process.env.POW_DIFFICULTY || '4', 10)));
const DOWNLOAD_DIR = process.env.DOWNLOAD_DIR || path.join(ROOT, 'downloads');
const TRUST_PROXY = process.env.TRUST_PROXY === '1';
try { fs.mkdirSync(DOWNLOAD_DIR, { recursive: true }); } catch { /* exists */ }

// platform -> installer filename expected inside DOWNLOAD_DIR
const PLATFORMS = { windows: 'ArchAssistantSetup-x64.exe', macos: 'ArchAssistant.dmg' };
// Optional: serve a platform from an upstream URL (e.g. a GitHub release asset)
// instead of a local file. Still gated by PoW ticket.
function pickUpstream(name, def) {
  if (!Object.prototype.hasOwnProperty.call(process.env, name)) return def;
  const v = (process.env[name] || '').trim();
  if (!v || /^(none|off|local)$/i.test(v)) return '';
  return v;
}
const UPSTREAM = {
  windows: pickUpstream('UPSTREAM_WINDOWS', ''),
  macos: pickUpstream('UPSTREAM_MACOS', ''),
};
for (const [plat, u] of Object.entries(UPSTREAM)) {
  if (!u) continue;
  let ok = false;
  try {
    const parsed = new URL(u);
    ok = parsed.protocol === 'https:' && /^(github\.com|objects\.githubusercontent\.com|release-assets\.githubusercontent\.com)$/.test(parsed.hostname);
  } catch { ok = false; }
  if (!ok) { console.warn(`[warn] ignoring unsafe UPSTREAM for ${plat}: ${u}`); UPSTREAM[plat] = ''; }
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};
// Never serve these, even if requested directly (source/config disclosure).
const DENY_BASENAMES = new Set(['server.mjs', 'package.json', 'package-lock.json', 'Caddyfile', 'DEPLOY.md', '.env']);

/* ---------------- small helpers ---------------- */
function now() { return new Date().toISOString(); }
const LOG_FILE = process.env.LOG_FILE || '';
function log(ip, method, url, code, note) {
  const line = `[${now()}] ${ip} ${method} ${url} -> ${code}${note ? ' (' + note + ')' : ''}\n`;
  console.log(line.trimEnd());
  if (LOG_FILE) { try { fs.appendFileSync(LOG_FILE, line); } catch { /* disk full? keep serving */ } }
}
function clientIp(req) {
  if (TRUST_PROXY) {
    const fwd = (req.headers['x-forwarded-for'] || '').split(',')[0].trim();
    if (fwd) return fwd.slice(0, 64);
  }
  return (req.socket.remoteAddress || 'unknown').slice(0, 64);
}
function baseHeaders(extra) {
  return Object.assign({
    'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'Content-Security-Policy': [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      "font-src 'self' https://fonts.gstatic.com",
      'img-src \'self\' data:',
      "connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; '),
  }, extra || {});
}
function send(res, req, code, body, type) {
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(body || '');
  const head = req.method === 'HEAD';
  res.writeHead(code, baseHeaders({
    'Content-Type': type || 'text/plain; charset=utf-8',
    'Content-Length': buf.length,
    'Cache-Control': 'no-store',
  }));
  res.end(head ? null : buf);
}
function sendJson(res, req, code, obj) {
  send(res, req, code, JSON.stringify(obj), 'application/json; charset=utf-8');
}

/* ---------------- rate limiter (in-memory token buckets) ---------------- */
const buckets = new Map(); // key -> {count, reset}
function checkLimit(ip, key, limit, windowMs) {
  const k = ip + '|' + key;
  const t = Date.now();
  let b = buckets.get(k);
  if (!b || t > b.reset) { b = { count: 0, reset: t + windowMs }; buckets.set(k, b); }
  b.count += 1;
  return { ok: b.count <= limit, retryAfter: Math.ceil((b.reset - t) / 1000) };
}
function denyLimited(res, req, ip, url, retryAfter) {
  res.writeHead(429, baseHeaders({ 'Content-Type': 'application/json; charset=utf-8', 'Retry-After': String(retryAfter), 'Cache-Control': 'no-store' }));
  res.end(JSON.stringify({ error: 'rate_limited', retry_after: retryAfter }));
  log(ip, req.method, url, 429, 'rate limit');
}
setInterval(() => {
  const t = Date.now();
  for (const [k, b] of buckets) if (t > b.reset) buckets.delete(k);
  for (const [tk, c] of challenges) if (t > c.exp) challenges.delete(tk);
  for (const [jti, exp] of usedTickets) if (t > exp) usedTickets.delete(jti);
}, 60 * 1000).unref();

/* ---------------- proof-of-work challenges + single-use tickets ---------------- */
const challenges = new Map(); // token -> {exp, ip}
const usedTickets = new Map(); // jti(mac) -> exp (for sweeping)
function sha256hex(s) { return crypto.createHash('sha256').update(s, 'utf8').digest('hex'); }
function powOk(token, nonce) {
  if (typeof nonce !== 'string' || !/^[0-9]{1,12}$/.test(nonce)) return false;
  return sha256hex(token + ':' + nonce).startsWith('0'.repeat(POW_DIFFICULTY));
}
function b64url(buf) { return Buffer.from(buf).toString('base64url'); }
function issueTicket(platform, ip, ctoken, nonce) {
  const exp = Date.now() + 90 * 1000;
  const payload = [exp, platform, ip, ctoken, nonce].join('|');
  const mac = crypto.createHmac('sha256', SECRET).update(payload, 'utf8').digest('hex');
  return b64url(payload) + '.' + mac;
}
function verifyTicket(ticket, platform, ip) {
  // returns 'ok' | 'bad' | 'expired' | 'reused'
  if (typeof ticket !== 'string') return 'bad';
  const parts = ticket.split('.');
  if (parts.length !== 2) return 'bad';
  let payload;
  try { payload = Buffer.from(parts[0], 'base64url').toString('utf8'); }
  catch { return 'bad'; }
  const fields = payload.split('|');
  if (fields.length !== 5) return 'bad';
  const [expS, plat, tip, ,] = fields;
  const exp = Number(expS);
  if (!Number.isFinite(exp) || Date.now() > exp) return 'expired';
  if (plat !== platform || tip !== ip) return 'bad';
  let macBuf, wantBuf;
  try { macBuf = Buffer.from(parts[1], 'hex'); } catch { return 'bad'; }
  wantBuf = Buffer.from(crypto.createHmac('sha256', SECRET).update(payload, 'utf8').digest('hex'), 'hex');
  if (macBuf.length !== wantBuf.length || !crypto.timingSafeEqual(macBuf, wantBuf)) return 'bad';
  if (usedTickets.has(parts[1])) return 'reused';
  return 'ok';
}
function consumeTicket(ticket) {
  usedTickets.set(ticket.split('.')[1], Date.now() + 90 * 1000);
}

/* ---------------- static files ---------------- */
function serveStatic(req, res, ip, pathname) {
  let rel;
  try { rel = decodeURIComponent(pathname); }
  catch { send(res, req, 400, 'Bad request'); log(ip, req.method, pathname, 400, 'bad encoding'); return; }
  if (rel === '/' || rel === '/index.html') rel = '/arch-assistant.html';
  const abs = path.normalize(path.join(ROOT, rel));
  if (!abs.startsWith(ROOT + path.sep)) { send(res, req, 404, 'Not found'); log(ip, req.method, pathname, 404, 'traversal'); return; }
  const base = path.basename(abs);
  if (base.startsWith('.') || DENY_BASENAMES.has(base)) { send(res, req, 404, 'Not found'); log(ip, req.method, pathname, 404, 'denied'); return; }
  const ext = path.extname(abs).toLowerCase();
  const type = MIME[ext];
  if (!type) { send(res, req, 404, 'Not found'); log(ip, req.method, pathname, 404, 'type'); return; }
  fs.stat(abs, (err, st) => {
    if (err || !st.isFile()) { send(res, req, 404, 'Not found'); log(ip, req.method, pathname, 404); return; }
    const head = Object.assign(baseHeaders({
      'Content-Type': type,
      'Content-Length': st.size,
      'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=86400',
    }));
    res.writeHead(200, head);
    log(ip, req.method, pathname, 200);
    if (req.method === 'HEAD') { res.end(); return; }
    fs.createReadStream(abs).on('error', () => { try { res.destroy(); } catch {} }).pipe(res);
  });
}

/* ---------------- router ---------------- */
function readBody(req, maxBytes) {
  return new Promise((resolve, reject) => {
    let n = 0;
    const chunks = [];
    req.on('data', (c) => { n += c.length; if (n > maxBytes) { reject(new Error('too_big')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const ip = clientIp(req);
  let url;
  try { url = new URL(req.url || '/', 'http://x'); }
  catch { send(res, req, 400, 'Bad request'); return; }
  const pathname = url.pathname;

  // --- well-known utility routes ---
  if ((req.method === 'GET' || req.method === 'HEAD') && (pathname === '/robots.txt' || pathname === '/sitemap.xml')) {
    // Reflect the public host so crawlers follow whichever address serves us.
    const host = String(req.headers['x-forwarded-host'] || req.headers.host || '').split(',')[0].trim() || 'localhost';
    const xfProto = String(req.headers['x-forwarded-proto'] || '').split(',')[0].trim();
    const proto = xfProto || (TRUST_PROXY ? 'https' : 'http');
    if (pathname === '/robots.txt') {
      send(res, req, 200, `User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /dl/\n\nSitemap: ${proto}://${host}/sitemap.xml\n`, 'text/plain; charset=utf-8');
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    send(res, req, 200,
      `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
      `<url><loc>${proto}://${host}/</loc><lastmod>${today}</lastmod><changefreq>weekly</changefreq></url>\n</urlset>\n`,
      'application/xml; charset=utf-8');
    return;
  }
  if ((req.method === 'GET' || req.method === 'HEAD') && pathname === '/.well-known/security.txt') {
    const exp = new Date(Date.now() + 365 * 864e5).toISOString().slice(0, 10);
    send(res, req, 200, `Contact: mailto:trevorkisingu@gmail.com\nExpires: ${exp}T00:00:00.000Z\nPreferred-Languages: en\n`, 'text/plain; charset=utf-8');
    return;
  }

  // --- 1) PoW challenge ---
  if (req.method === 'GET' && pathname === '/api/challenge') {
    const rl = checkLimit(ip, 'challenge', 30, 60 * 1000);
    if (!rl.ok) { denyLimited(res, req, ip, pathname, rl.retryAfter); return; }
    const token = crypto.randomBytes(16).toString('hex');
    challenges.set(token, { exp: Date.now() + 5 * 60 * 1000, ip });
    sendJson(res, req, 200, { token, difficulty: POW_DIFFICULTY, expires_in: 300 });
    log(ip, req.method, pathname, 200);
    return;
  }

  // --- 2) redeem solution for a one-time ticket ---
  if (req.method === 'POST' && pathname === '/api/token') {
    const rl = checkLimit(ip, 'token', 20, 60 * 1000);
    if (!rl.ok) { denyLimited(res, req, ip, pathname, rl.retryAfter); return; }
    let body;
    try { body = JSON.parse(await readBody(req, 2048)); }
    catch { sendJson(res, req, 400, { error: 'bad_request' }); log(ip, req.method, pathname, 400); return; }
    const { token, nonce, platform } = body || {};
    if (!Object.prototype.hasOwnProperty.call(PLATFORMS, platform)) {
      sendJson(res, req, 400, { error: 'bad_platform' }); log(ip, req.method, pathname, 400, 'platform'); return;
    }
    const ch = challenges.get(token);
    challenges.delete(token); // single attempt per challenge
    if (!ch || Date.now() > ch.exp || ch.ip !== ip || !powOk(token, nonce)) {
      sendJson(res, req, 403, { error: 'forbidden' }); log(ip, req.method, pathname, 403, 'bad pow/challenge'); return;
    }
    const ticket = issueTicket(platform, ip, token, nonce);
    sendJson(res, req, 200, { ticket, expires_in: 90 });
    log(ip, req.method, pathname, 200, platform);
    return;
  }

  // --- 3) ticketed download (streaming, single-use) ---
  let dlMatch = null;
  if ((req.method === 'GET' || req.method === 'HEAD') && (dlMatch = pathname.match(/^\/dl\/(windows|macos)$/))) {
    const platform = dlMatch[1];
    const rl = checkLimit(ip, 'download', 8, 60 * 60 * 1000);
    if (!rl.ok) { denyLimited(res, req, ip, pathname, rl.retryAfter); return; }
    const verdict = verifyTicket(url.searchParams.get('ticket'), platform, ip);
    if (verdict !== 'ok') {
      sendJson(res, req, 403, { error: 'forbidden' }); log(ip, req.method, pathname, 403, 'ticket ' + verdict); return;
    }
    if (UPSTREAM[platform]) {
      // Ticket is valid: hand the client to the upstream release asset.
      // Consume on GET so each solved challenge yields exactly one download.
      if (req.method === 'GET') consumeTicket(url.searchParams.get('ticket'));
      res.writeHead(302, baseHeaders({ Location: UPSTREAM[platform], 'Cache-Control': 'no-store' }));
      res.end();
      log(ip, req.method, pathname, 302, platform + ' -> upstream');
      return;
    }
    const file = path.join(DOWNLOAD_DIR, PLATFORMS[platform]);
    fs.stat(file, (err, st) => {
      if (err || !st.isFile()) {
        sendJson(res, req, 410, { error: 'not_published' }); log(ip, req.method, pathname, 410, 'no binary yet'); return;
      }
      if (req.method === 'GET') consumeTicket(url.searchParams.get('ticket'));
      res.writeHead(200, baseHeaders({
        'Content-Type': 'application/octet-stream',
        'Content-Length': st.size,
        'Content-Disposition': `attachment; filename="${PLATFORMS[platform]}"`,
        'Cache-Control': 'no-store',
      }));
      log(ip, req.method, pathname, 200, platform + ' ' + st.size + 'b');
      if (req.method === 'HEAD') { res.end(); return; }
      fs.createReadStream(file).on('error', () => { try { res.destroy(); } catch {} }).pipe(res);
    });
    return;
  }

  // --- static site ---
  if (req.method === 'GET' || req.method === 'HEAD') { serveStatic(req, res, ip, pathname); return; }
  send(res, req, 405, 'Method not allowed'); log(ip, req.method, pathname, 405);
});

server.requestTimeout = 15000;
server.maxRequestsPerSocket = 200; // bound keep-alive reuse per connection
// Last-resort guard: log instead of dying on any unforeseen throw, so one
// malformed request can never take the whole site down again.
process.on('uncaughtException', (err) => {
  try { console.error(`[${now()}] UNCAUGHT`, err && err.stack || err); } catch { /* ignore */ }
});
process.on('unhandledRejection', (reason) => {
  try { console.error(`[${now()}] UNHANDLED REJECTION`, reason); } catch { /* ignore */ }
});
server.listen(PORT, () => console.log(`[ready] Arch Assistant on :${PORT} (PoW difficulty ${POW_DIFFICULTY})`));
