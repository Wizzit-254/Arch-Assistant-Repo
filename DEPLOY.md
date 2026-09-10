# Launching arch-assistant.com (or .dev) — runbook

> Honest note: I can't buy a domain or push anything live for you — that needs
> your registrar account, your payment, and a server you control. Everything
> below is ready; follow the steps and the site goes live over HTTPS in ~30 min.

Domain status (checked 2026-09-10): **no DNS records** for `arch-assistant.com`
or `arch-assistant.dev`, and the `.com` RDAP registry returns 404
(unregistered). Both *look* free, but confirm at checkout — someone may grab
either at any time.

## 1. Buy the domain (5 min, ~$10–15/yr)
1. Registrar: Cloudflare Registrar, Porkbun, or Namecheap (any works).
2. Search `arch-assistant.com` first (`.com` is the safer pick), `.dev` as backup
   (note: `.dev` is HSTS-preloaded — HTTPS-only, which is what we want anyway).
3. Buy it. Enable registrar lock + WHOIS privacy (usually free).

## 2. Point DNS at your server (2 min + propagation)
You need one small VPS (Hetzner CX22 / DigitalOcean droplet / etc., Ubuntu 24.04).
In the registrar's DNS panel:
- `A  @  <server-ipv4>` and `AAAA  @  <server-ipv6>` (if you have one)
- `A  www  <server-ipv4>` (+ AAAA ditto)
- TTL 300 while testing, raise later.

## 3. Server setup (10 min)
```bash
# Node 20+ and Caddy
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
sudo apt install -y caddy

# Ship this folder to /srv/arch (scp/rsync/git — your choice)
#  Installers: Windows x64 uses a staged installer (ArchAssistantSetup-x64.exe, ~10MB)
#   that displays T&C acceptance, lets user choose install location,
#   then downloads the full 5GB model bundle Stage 2.
#   macOS uses ArchAssistant-LightInstaller-macOS.sh (staged).
#   UPSTREAM_WINDOWS defaults to the GitHub release asset
#   (override with env to pin a newer tag).

# Secret every boot should NOT regenerate in prod — set one:
export ARCH_SECRET="$(openssl rand -hex 32)"   # put in the systemd unit below
export TRUST_PROXY=1                            # we sit behind Caddy
export PORT=8080
```

systemd unit `/etc/systemd/system/arch.service`:
```ini
[Unit]
Description=Arch Assistant site
After=network.target

[Service]
WorkingDirectory=/srv/arch
Environment=PORT=8080
Environment=TRUST_PROXY=1
Environment=ARCH_SECRET=paste-a-long-random-hex-here
ExecStart=/usr/bin/node server.mjs
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now arch
sudo cp Caddyfile /etc/caddy/Caddyfile   # edit the domain if you took .dev
sudo systemctl reload caddy              # HTTPS certs are automatic
```

## 4. Verify the launch
```bash
curl -sI https://arch-assistant.com | grep -iE 'strict|content-security|x-frame|x-content'
curl -s https://arch-assistant.com/robots.txt
curl -s -o /dev/null -w '%{http_code}\n' https://arch-assistant.com/server.mjs  # must be 404
# Full PoW roundtrip: challenge -> solve (find nonce with N leading zeros) ->
# POST /api/token -> HEAD /dl/windows?ticket=... -> 200, reuse -> 403
```

## 5. Security model (what's actually protected)
- **Bot-gated downloads:** every installer fetch costs a SHA-256 proof-of-work
  (~1s real-browser CPU), plus a 90-second single-use HMAC ticket bound to the
  requester's IP, plus 8 downloads/hour/IP. Casual scrapers, hotlinkers, and
  mass-leech scripts bounce off; nothing here stops a *determined, funded*
  attacker — no purely technical gate can. The binaries themselves must still
  be signed (Windows Authenticode / Apple notarization) so users can trust them.
- **Headers on every response:** HSTS (preload-ready), CSP, `X-Frame-Options:
  DENY`, `nosniff`, strict `Referrer-Policy`, locked-down `Permissions-Policy`.
- **No source disclosure:** `server.mjs`, `package.json`, `Caddyfile`,
  `DEPLOY.md`, dotfiles, and raw installer paths all 404. Installers ONLY
  stream through `/dl/*` with a valid ticket.
- **Static page hygiene:** no inline event handlers, all outbound links use
  `rel="noopener noreferrer"`, legal docs render same-origin (no third-party
  readers), Google Fonts is the only external dependency (pinned in CSP).
- **Ops:** keep Node + Caddy patched (`apt upgrade`), back up `ARCH_SECRET`
  rotation plan (restart = all tickets invalidate, harmless), watch logs for
  403/429 bursts.
