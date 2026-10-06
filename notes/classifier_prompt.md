# Classifier prompt (Haiku)

Give the agent the text between the lines below, with `{INPUT}` and `{OUTPUT}` filled in. Input: `data/labels/topic_batches/batch_NN.jsonl`. Output: `data/labels/topic_labels/batch_NN.jsonl` (create the directory first). Full reasoning behind the rules is in `docs/taxonomy.md`; this file is self-contained.

---

You label pull requests to Omarchy (an opinionated Arch Linux + Hyprland desktop; Omarchy 4 "Quattro" added a Quickshell shell with bar, panels and plugins; before that the bar was Waybar, the launcher Walker, notifications Mako).

TASK
1. Read the file {INPUT}. Each line is JSON: {"number", "title", "body"} (body is the first 600 characters, may be empty).
2. For every line write one JSON line to {OUTPUT}: {"number": N, "kind": "...", "topic": "...", "confidence": "high|medium|low"}. Exactly one output line per input line, same order, same number. No other keys, no commentary.
3. Work in chunks of 50 PRs: write the first chunk with a Bash heredoc to {OUTPUT} (`cat > file <<'EOF'`), later chunks with `cat >> file <<'EOF'`. Do not skip, merge or invent PRs.
4. Finish by running `wc -l {INPUT} {OUTPUT}`; the two counts must match. If not, find and fill the missing numbers.

Use only title and body. Judge what the PR changes, not how well it is written. Do not guess from the PR number. Never leave a field empty; if unsure, choose the best value and lower the confidence.

TOPIC (pick one id; use the first rule that settles it, then the lowest P if still tied)
P1 hardware_drivers: a specific device, laptop model, chip, kernel module, firmware or driver; disk/drive tools. A named model or chip as the cause wins over the symptom area.
P2 security_auth: sudo, passwords, PAM, polkit, SSH keys, firewall, package signing, permission hardening, face/fingerprint login flow.
P3 power_session: suspend, hibernate, lid, idle, lock timing, screensaver behaviour, battery, power profiles, logout, shutdown, login manager.
P4 install_update: installer, ISO, bootloader (Limine), filesystem/snapshots at install, first boot, locale/keymap at setup, omarchy update, channels, release notes, migration machinery.
P5 display_capture: monitors, scaling, brightness, night light, HDR; screenshots, screen recording, screen sharing, region picker, screen OCR.
P6 audio_media: audio devices/profiles, volume, mic mute, media keys, players, webcam, voice dictation (Voxtype), transcoding.
P7 networking: Wi-Fi, Ethernet, Bluetooth, VPN/Tailscale, DNS, printers, captive portal.
P8 agents_ai: in-product AI tooling: omarchy-agent, default agent picker, agent usage collectors/panel, local-model panel.
P9 hyprland_windowing: window rules (including for a named app), floating/tiling, layouts, workspaces, keybindings, gestures, keyboard layout, touchpad/mouse settings, Hyprland syntax compatibility.
P10 theming_appearance: themes, wallpapers, colour templates, theme sync into third-party apps, fonts, icons, branding.
P11 terminal_dev_env: terminal emulators, bash/zsh, prompt, aliases, tmux, git, editors, mise, dev language installers (Install > Development/Editor/DevOps).
P12 apps_packages: package lists, Install/Remove menu entries for other apps, web apps and launcher, browsers and flags, Steam/games, Docker, Windows VM, desktop entries.
P13 shell_ui: look and behaviour of shell surfaces: bar, tray, popups, panel chrome, notifications, OSD, menu search/navigation/glyphs, plugin framework, clock/workspace/weather widgets, shell translations, lock-screen and screensaver visuals.
P14 cli_repo_misc: `omarchy` CLI plumbing (dispatcher, help, hooks), dev/test tooling, CI, contributor docs, AGENTS.md and agent skills, licence, manual and its translations, repo housekeeping, empty or unreadable PRs.

Topic rules
- Presentation of a shell element (colour, size, rendering, animation, glyph) is shell_ui. Logic/data of a domain (update check, battery value, Bluetooth state, audio profile) goes to that domain even if shown in the bar.
- A migration for X takes X's topic; only migration machinery in general is install_update.
- Docs about X take X's topic; repo-wide docs, AGENTS.md and anything for AI agents working on the repo are cli_repo_misc.
- Theme sync into an app (VS Code, Obsidian, Zen) is theming_appearance.
- Fingerprint sensor drivers/packages are hardware_drivers; the lock/sudo/polkit login flow is security_auth.
- Several areas in one PR: use the one named first in the title, else the one with most of the change.
- Empty body and a title that names no area ("Master", "Fix/auto install"): topic cli_repo_misc, kind other, confidence low.

KIND (pick the first that fits)
1 docs: only docs, comments, manual, README, licence change. A typo in a user-visible string (menu label, keybinding description) is bug_fix.
2 packaging: mainly adding/removing/swapping/pinning/re-sourcing a package or an Install-menu entry; ISO mirror or package-list entry; no new logic beyond that.
3 security: stated purpose is hardening or closing a vulnerability (permissions, signatures, credential exposure, privilege grants, injection).
4 performance: stated purpose is speed, CPU, memory, IO, latency, battery drain.
5 refactor: restructuring with no intended behaviour change.
6 bug_fix: corrects something described as broken: crash, regression, wrong output, failed migration, UI typo, revert of a faulty change.
7 feature: adds a capability, option, binding, theme, wallpaper, app, device support, or deliberately changes a default.
8 other: empty or unreadable, housekeeping, salvage or tracking PRs.
A PR that both fixes and adds is judged by its title.

CONFIDENCE (one value for the pair; use the lower of your topic and kind certainty)
high: one reading is clearly best. medium: a second topic or kind is defensible. low: title and body give almost nothing, or the PR mixes unrelated areas.
Expect roughly 70% high, 25% medium, 5% low. Do not mark everything high.

EXAMPLES (title -> topic, kind)
"Fix ASUS ExpertBook B9406 touchpad quirk never being applied" -> hardware_drivers, bug_fix
"Clear passwordless sudo grants at boot" -> security_auth, security
"Add delayed hibernate after suspend" -> power_session, feature
"Set Limine template and config default_entry to 1" -> install_update, bug_fix
"fix: prevent crosshair cursor from appearing in screenshots" -> display_capture, bug_fix
"Add audio profile list/set so HDMI outputs are selectable from the shell" -> audio_media, feature
"Reopen the wifi passphrase prompt after a wrong saved password" -> networking, bug_fix
"Add Kilo AI" (default coding agent) -> agents_ai, feature
"fix: adds "Open Directory" to the floating-window windowrule" -> hyprland_windowing, bug_fix
"Add Running Buck wallpaper to Catppuccin theme" -> theming_appearance, feature
"Update omarchy-install-dev-env with Zig" -> terminal_dev_env, feature
"Switch to Brave Origin Stable version from Brave Origin Beta" -> apps_packages, packaging
"Keep the bar mapped while hidden so revealing it is instant" -> shell_ui, performance
"Fix and expand the omarchy agent skill" -> cli_repo_misc, docs
"Master" (empty body) -> cli_repo_misc, other, low

OUTPUT LINE EXAMPLE
{"number": 6677, "kind": "performance", "topic": "shell_ui", "confidence": "high"}

---

Allowed values (any other string is an error)
- kind: bug_fix, feature, performance, refactor, docs, packaging, security, other
- topic: hardware_drivers, security_auth, power_session, install_update, display_capture, audio_media, networking, agents_ai, hyprland_windowing, theming_appearance, terminal_dev_env, apps_packages, shell_ui, cli_repo_misc
- confidence: high, medium, low
