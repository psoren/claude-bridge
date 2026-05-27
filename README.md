# bridge — MBP-Claude ↔ Mini-Claude IPC

![Cross-section pixel-art of a house at night: laptop on the desk downstairs glows, a thin gold thread snakes up through the floor to a sleeping bedroom upstairs](./hero.png)

A 70-line Python HTTP server on the mini, plus a one-liner CLI on the MBP. Lets a Claude session on the laptop delegate a prompt to a Claude session on the mini and get the response back.

## Why

`ssh parkers-mac-mini "claude -p ..."` won't work directly. macOS stores Claude's OAuth token in the login Keychain, and a fresh SSH session inherits a *locked* Keychain — `claude` reports "Not logged in" even though the GUI session is fully authenticated.

This bridge sidesteps that. The daemon is launched once **inside a GUI Terminal on the mini** (where Keychain is unlocked) and runs forever. SSH sessions don't talk to `claude` directly — they curl the daemon over loopback.

```
[ MBP zsh ]
    │ ssh + key auth
    ▼
[ mini sshd ]
    │ curl POST http://127.0.0.1:9100/ask
    ▼
[ bridge daemon ]    ← started in GUI terminal → Keychain unlocked
    │ subprocess: claude -p "<prompt>"
    ▼
[ Claude on mini ]
```

## One-time setup on the mini

**Prerequisite — the Keychain ACL is open.** Open Keychain Access → search `Claude Code-credentials` → Access Control → "Allow all applications to access this item". Without this, any non-GUI process (including LaunchAgents) will hit a Keychain prompt and fail.

Once the ACL is open, the simplest install is the LaunchAgent in the "Persisting" section below. It runs in your user session at login, so it inherits the unlocked login Keychain. If you'd rather sanity-check it first, run it in the foreground in a GUI terminal:

```bash
python3 ~/github/claude-bridge/server.py
# should print: claude-bridge listening on 127.0.0.1:9100
```

## Use from the MBP

```bash
~/github/claude-bridge/ask-mini "list the dirs under ~/github on this host"
```

Or pipe a prompt in:

```bash
echo "summarize the contents of ~/projects/foo/HANDOFF.md" | ~/github/claude-bridge/ask-mini -
```

## Persisting (launchd)

Drop at `~/Library/LaunchAgents/com.parker.claude-bridge.plist` on the mini:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>com.parker.claude-bridge</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/parker/github/claude-bridge/server.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <!-- launchd's default PATH is the bare /usr/bin:/bin:/usr/sbin:/sbin and
         won't find `claude` no matter where it lives. Include every plausible
         install location. Order matters: cmux.app first because that's where
         the bundled binary lives on Parker's mini; then Homebrew; then npm
         (in case you `npm install -g @anthropic-ai/claude-code`). -->
    <key>PATH</key>
    <string>/Applications/cmux.app/Contents/Resources/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key>        <true/>
  <key>KeepAlive</key>        <true/>
  <key>StandardOutPath</key>  <string>/tmp/claude-bridge.out.log</string>
  <key>StandardErrorPath</key><string>/tmp/claude-bridge.err.log</string>
</dict>
</plist>
```

After editing the plist, reload:

```bash
launchctl unload ~/Library/LaunchAgents/com.parker.claude-bridge.plist
launchctl load   ~/Library/LaunchAgents/com.parker.claude-bridge.plist
```

Load: `launchctl load ~/Library/LaunchAgents/com.parker.claude-bridge.plist`.

Tail the log to confirm: `tail -f /tmp/claude-bridge.err.log` should show `claude-bridge listening on 127.0.0.1:9100`.

## Threat model

The daemon binds to `127.0.0.1` only. Anyone with shell access on the mini can hit it; anyone with SSH access on the mini (you, via your Tailnet key) can hit it via the SSH tunnel. There is no auth on the endpoint itself — the security boundary is "can SSH into the mini." If you want belt-and-braces, add a shared-secret header check in `server.py`.

## Related projects

These both predate this one and have overlapping goals. I learned about them *after* building this — so this section exists for intellectual honesty, not as a "compare and contrast." They're all valid; pick whichever fits your shape best.

- **[willjackson/claude-code-bridge](https://github.com/willjackson/claude-code-bridge)** — same name as this one (whoops). Extends Claude Code to remote machines via WebSocket with TLS, tokens, and auth. More elaborate than ours and supports file operations as well as prompt delegation.
- **[rohitg00/tailclaude](https://github.com/rohitg00/tailclaude)** — Claude Code on your Tailnet, powered by the "iii engine." Tailscale-specific, so it's the closest geographic match to this setup.

I still think this one is worth having around for three reasons:

- **Minimal architecture.** ~70 lines of Python, no protocol, no client library, no auth tokens. Easy to read end-to-end and easy to audit.
- **OAuth-subscription-aware.** Works with your Claude Code Max subscription on the always-on machine instead of forcing an `ANTHROPIC_API_KEY` (which would bill at API rates).
- **Sidesteps Keychain instead of solving it.** The common fix is to configure SSH to unlock the login keychain on connect. This one avoids the problem by never having SSH invoke `claude` at all — a daemon born in the GUI session does the OAuth read, and SSH just curls loopback.
