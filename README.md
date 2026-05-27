# bridge — MBP-Claude ↔ Mini-Claude IPC

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
