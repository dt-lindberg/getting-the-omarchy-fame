# Taxonomy for community PRs

Applied by a Haiku classifier to one PR at a time, from the title plus the first 600 characters of the body. Two independent labels per PR: `topic` (which area of the product) and `kind` (what sort of change). Exactly one value of each. Never use the file list, labels or review state (not available to the classifier, and would leak outcome).

Population: all 6,339 community PRs (author not in dhh, ryanrhughes, spencerbull, bjarneo, ErikMelton, birkskyum, emirb, nor a bot; checked: no community author has merged another person's PR). All states.

## Product map (what the code areas are)
- `shell/` (Quickshell, Omarchy 4 "Quattro"): `shell.qml`, plugins for bar, panels (network, Bluetooth, audio, agents, Tailscale, weather, monitors...), menu, notifications, OSD, lock, clipboard, emojis, polkit, reminders. Replaces the pre-Quattro Waybar + Walker + Mako + SwayOSD stack, which most 2025 PRs touch.
- `config/` and `default/`: Hyprland (now Lua) config, window rules, bindings, hypridle, terminals, tmux, fonts, Plymouth, SDDM, Limine, udev, systemd units.
- `bin/omarchy-*`: about 300 scripts grouped by prefix (install, theme, hw, launch, toggle, agent, menu, pkg, audio, capture, brightness...). The `omarchy` command dispatches to them.
- `install/`: installer steps (config, hardware quirks, login, post-install), package lists. `migrations/`: one script per upgrade step.
- `themes/`, `manual/`, `agents/skills/` and `AGENTS.md` (instructions for AI coding agents working on the repo).

## `topic`: 14 categories

Decision procedure: read title, then body; pick the area whose behaviour the PR changes. Apply the rules R1-R11 below, then, if still tied, take the category with the lower precedence number (P) in the table. A PR touching several areas gets the one named first in the title, else the one with most of the described change.

| P | id | Definition |
|---|----|-----------|
| 1 | `hardware_drivers` | Support for a specific device, laptop model, chip, kernel module, firmware or driver; also drives/disks tools. |
| 2 | `security_auth` | Authentication and access control: sudo, passwords, PAM, polkit, SSH keys, firewall, package signing, permissions hardening, face or fingerprint login flow. |
| 3 | `power_session` | Suspend, hibernate, lid, idle, lock timing, screensaver behaviour, battery, power profiles, logout, shutdown, login manager. |
| 4 | `install_update` | Installer and ISO, bootloader, filesystem and snapshots at install time, first boot, locale and keymap at setup, `omarchy update`, channels, migration machinery, release notes. |
| 5 | `display_capture` | Monitors, scaling, brightness, night light, HDR; screenshots, screen recording, screen sharing, region pickers, OCR from the screen. |
| 6 | `audio_media` | Audio devices and profiles, volume and mic mute, media keys, players, camera, voice dictation (Voxtype), video and image conversion. |
| 7 | `networking` | Wi-Fi, Ethernet, Bluetooth, VPN and Tailscale, DNS, network printers and file sharing, captive portals. |
| 8 | `agents_ai` | Product features for AI coding tools: `omarchy-agent`, default agent picker, agent usage collectors and panel, local-model panel, agent launching and env. |
| 9 | `hyprland_windowing` | Window rules, floating or tiling, layouts, workspaces, keybindings, gestures, keyboard layout, touchpad and mouse settings, Hyprland version compatibility. |
| 10 | `theming_appearance` | Themes, wallpapers, colour templates, app theme sync, fonts, icons, cursor, branding, logo, visual identity. |
| 11 | `terminal_dev_env` | Terminal emulators, shell (bash, zsh), prompt, aliases, tmux, git, Neovim and other editors, dev language environments, mise, CLI tools for developers. |
| 12 | `apps_packages` | Which apps and packages ship or can be installed, and how they launch: package lists, Install and Remove menus, web apps, browsers, Steam and games, Docker, Windows VM, per-app config and flags. |
| 13 | `shell_ui` | Generic look and behaviour of shell surfaces: bar, tray, popups, panel chrome, notifications and OSD, menu mechanics (search, navigation, ranking, glyphs), plugin framework, shell translations. |
| 14 | `cli_repo_misc` | `omarchy` CLI plumbing (dispatcher, help, hooks), dev and test tooling, CI, contributor docs, AGENTS.md and agent skills, licence, manual, translations of the manual, repo housekeeping, unclassifiable or empty PRs. |

### Rules (each was added because a validation case needed it)
- R1 Subject over surface. Presentation of a shell element (colour, size, rendering, layout, animation, glyph, menu behaviour) is `shell_ui`. Logic or data of a domain (update check, battery value, Bluetooth state, audio profile) goes to that domain even when it is shown in the bar or a panel. Lock-screen and screensaver visuals are `shell_ui`; when to lock or idle is `power_session`.
- R2 Window rules, floating rules, opacity rules and app-id matching for a named app are `hyprland_windowing`, unless the PR mainly installs or packages the app.
- R3 Syncing a theme into a third-party app (VS Code, Obsidian, Zen, Pi) is `theming_appearance`.
- R4 A migration for X takes X's topic. Only migration machinery, ordering or failure handling in general is `install_update`.
- R5 Docs about X take X's topic with kind `docs`. Repo-wide docs (README, licence, contributing, AGENTS.md, anything under `agents/skills/`, manual translations) are `cli_repo_misc`.
- R6 Docker, Windows VM, RDP, Steam, Wine and app launchers: `apps_packages`. Tailscale itself is `networking`.
- R7 Disk and drive tools (format, password, info) are `hardware_drivers`. Choice of filesystem or snapshots during install is `install_update`.
- R8 Empty body and a title that names no area ("Master", "Fix/auto install"): `cli_repo_misc`, kind `other`, confidence `low`. A vague title that still names an area ("added wallpaper") takes that area.
- R9 Several areas in one PR: use the one in the title, else the one with most of the described change. Do not invent a mixed label.
- R10 Hardware named as the cause (a laptop model, chip, kernel module, firmware) wins over the symptom area: Bluetooth on T2 Macs and speaker drivers are `hardware_drivers`. A generic fix that merely mentions a GPU or laptop in passing is not.
- R11 Fingerprint sensor drivers and packages are `hardware_drivers`; the lock, sudo or polkit login flow is `security_auth`.

### Per-category rules and real examples

`hardware_drivers`: include model-specific quirks (ASUS, Framework, Dell XPS, ThinkPad, Apple T2, Surface), GPU and Nvidia driver choice, firmware, udev and kernel modules, keyboard RGB, drive tools. Exclude generic features that happen to be tested on one laptop. Wins over every other topic (R10).
- 5435 Add ASUS ExpertBook B9406 display and touchpad fixes for Panther Lake
- 7140 Install CS8409 speaker driver on 2016-2017 MacBook Pros
- 5145 Fix Bluetooth on T2 Macs by loading hci_bcm4377 module

`security_auth`: include sudo and passwordless grants, PAM, SSH hardening, firewall rules, package authenticity, file permissions, credential leaks. Exclude pure fingerprint hardware (R11). Loses to `hardware_drivers` only.
- 9460 [codex] OM-SEC-04: Require package authenticity during Quattro
- 13575 Bound the package-install sudo keepalive and revoke it on exit
- 7990 Clear passwordless sudo grants at boot

`power_session`: include idle and lock timeouts, suspend and hibernate, lid handling, clamshell, battery notifications, power profiles, screensaver triggers and inhibitors. Exclude lock-screen looks (`shell_ui`), monitor scale after wake (`display_capture` if the symptom is scale, else here).
- 10408 Stop the screensaver interrupting video playback
- 5041 Add delayed hibernate after suspend
- 10081 Latch the low-battery warning until the battery recovers

`install_update`: include installer flow, ISO contents, Limine and boot entries, Btrfs and Snapper setup, locale at setup, `omarchy update` behaviour, update indicators and release notes, migration failure handling. Exclude per-app migrations (R4).
- 12804 Set Limine template and config default_entry to 1
- 10949 Ask for a language at setup, and offer one in the menu
- 9285 Clear unowned running-kernel modules leftovers during update

`display_capture`: include monitor config and scaling, DDC brightness, night light, HDR, screenshot, screen recording, share picker, OCR, cursor in captures. Exclude Hyprland workspace-to-monitor bindings (`hyprland_windowing`).
- 4874 feature/add 1.25 scaling toggle
- 6212 fix: prevent crosshair cursor from appearing in screenshots
- 7532 Fall back to the portal backend when kms can't capture the monitor

`audio_media`: include PipeWire and WirePlumber, sinks, profiles, mic mute, volume keys, media players, webcam, Voxtype dictation, transcoding. Exclude Bluetooth pairing (`networking`).
- 14082 Add audio profile list/set so HDMI outputs are selectable from the shell
- 5540 fix: reliable mic mute fallback using wpctl
- 941 Add SUPER + MUTE for audio output switching

`networking`: include Wi-Fi and iwd or NetworkManager, Bluetooth device handling, Tailscale, DNS, printers, captive portal.
- 13806 Retain Bluetooth controls when unpowered and cap discovery retry
- 6584 Reopen the wifi passphrase prompt after a wrong saved password
- 9277 Send clipboard contents to a tailnet machine with Taildrop

`agents_ai`: include in-product AI tooling only. Exclude instructions written for agents that work on the repo (R5, `cli_repo_misc`) and generic AI apps in Install menus (`apps_packages`).
- 10240 agent-usage-update: discover user-level collectors in $XDG_BIN_HOME or ~/.local/bin
- 11129 Add Kilo AI
- 8836 Add a first-party Local AI panel for registry-backed model serving

`hyprland_windowing`: include `windowrule`s, bindings (including new shortcuts for any feature, if the binding is the PR), workspace behaviour, gestures, keyboard layout and touchpad settings, Hyprland syntax breakage.
- 838 adds: incremental workspace and window management bindings
- 5023 fix: adds "Open Directory" to the xdg-desktop-portal-gtk floating-window tag windowrule
- 3010 Add Super+Shift+~ keybinding to move workspace between monitors

`theming_appearance`: include theme packs, palette changes, wallpapers, theme templates and per-app sync, fonts, icons, logo and branding art, theme-switch mechanics.
- 4547 Allow user themes to override individual files from official themes
- 9363 Improve Obsidian theme syncing with auto-activation, hot-reloading snippets, and contrast fixes
- 4231 Add Running Buck wallpaper to Catppuccin theme

`terminal_dev_env`: include terminal emulator config, bash or zsh, aliases, Starship, tmux, git, editors, mise, dev environment installers (Install > Development, Editor, DevOps).
- 5247 Run Omarchy's npx wrappers through mise-managed Node
- 595 Update omarchy-install-dev-env with Zig
- 4877 Fix try interactive selector appearing on bashrc re-source

`apps_packages`: include package list edits, Install and Remove menu entries for non-developer apps, web apps and the web-app launcher, browser flags and policy, Steam and gaming, Docker, Windows VM, desktop entries.
- 6021 Switch to Brave Origin Stable version from Brave Origin Beta
- 4571 Steam: install gpu deps + gamemode and gamescope
- 6077 Fix Microsoft Edge web apps failing to launch

`shell_ui`: include Quickshell and Waybar rendering, bar widgets that only show data (clock, workspaces, tray, weather), popups, toasts, OSD, menu search and navigation, plugin loader and API, shell translations. Exclude domain logic (R1).
- 6677 Keep the bar mapped while hidden so revealing it is instant
- 9245 Fix context menus for Wine tray items
- 7445 shell: close menu-spawned panels on toggle re-press instead of re-running the action

`cli_repo_misc`: catch-all. Include `omarchy` command table, help output, hooks, dev tooling and tests, agent skills, AGENTS.md, licence, manual, translations of the manual, spam or empty PRs.
- 10847 fix: clamp omarchy commands table to terminal width
- 5902 Simplify omarchy-dev-add-migration and make it possible to override OMARCHY_PATH for dev
- 13735 Fix and expand the omarchy agent skill

## `kind`: 8 values

Apply the first that fits, in this order of precedence.

| P | id | Rule |
|---|----|------|
| 1 | `docs` | Only documentation, comments, manual, README, licence or translation of those change. A typo in a user-visible string (menu label, keybinding description) is `bug_fix`, not `docs`. |
| 2 | `packaging` | The change is mainly adding, removing, swapping, pinning or re-sourcing a package or an Install-menu entry for it, or an ISO mirror or package-list entry. No new logic beyond that. |
| 3 | `security` | Stated purpose is hardening or closing a vulnerability: permissions, signatures, credential exposure, privilege grants, injection. |
| 4 | `performance` | Stated purpose is speed, CPU, memory, IO, latency, battery drain or start-up time. |
| 5 | `refactor` | Stated to change structure with no intended behaviour change (splitting a file, renaming, simplifying). |
| 6 | `bug_fix` | Corrects behaviour described as broken: crash, regression, wrong output, failed migration, typo in a UI string, a revert of a faulty change. |
| 7 | `feature` | Adds a capability, option, binding, theme, wallpaper, app, device support, or deliberately changes a default. |
| 8 | `other` | Empty or unreadable, housekeeping that fits nothing above, salvage or tracking PRs. |

Notes: a fix to a theme or window rule is still `bug_fix`. New hardware support that adds logic is `feature`; if it only adds a package it is `packaging`. A PR that both fixes and adds is judged by its title.

## Validation (60 random PRs, seed 2024, labelled by hand)

Labels with notes: `data/labels/taxonomy_validation.tsv`.

- First pass (before R1-R11): 22 of 60 (37%) had a second defensible topic. Seven of those changed label once the rules existed (R1 update indicators, R2 window rules for named apps, R3 Pi theme, R4 tmux migration, R5 agent-facing docs); R1 and R7 also settled the menu-glyph and drive cases.
- After rules: 16 of 60 (27%) still medium or low on topic, 3 of them low (empty or mixed PRs). Residual causes: PRs that mix areas (Nautilus context menu for transcode, project scratchpad), config PRs that touch two apps (Waybar plus Ghostty), and sudo or fingerprint PRs on the border of `security_auth`.
- Kind: 10 of 60 (17%) medium or low. Main confusion: `feature` against `bug_fix` for behaviour tweaks ("turn displays off on lock only in power-saving modes") and `packaging` against `feature`/`bug_fix` for package-stack changes.
- Expected agreement of a Haiku classifier with a careful human: topic about 70-75%, kind about 80-85% (95% interval on these rates is roughly plus or minus 10 points with n=60). Treat `confidence` low/medium as the marker: expect about 25-30% of topic labels and 15-20% of kind labels to be medium or low.
- Tally of the 60 by topic: shell_ui 10, cli_repo_misc 8, install_update 6, hyprland_windowing 6, theming_appearance 6, power_session 5, terminal_dev_env 4, apps_packages 4, display_capture 3, networking 2, hardware_drivers 2, security_auth 2, agents_ai 1, audio_media 1. By kind: feature 24, bug_fix 24, docs 3, refactor 2, packaging 2, security 2, other 2. Small categories (`agents_ai`, `audio_media`) are under-represented in a sample this small; the 433-PR read-through shows agents_ai is larger in Aug-Oct 2026 (Quattro agent panel, collectors).
- Use for analysis: topics are coarse enough to be stable (no category above 17% in the sample) but `shell_ui`, `cli_repo_misc` and `apps_packages` take the overflow, so check effects on those three for label noise before interpreting them.
- Epoch caveat: before Quattro (Aug 2026) "bar" means Waybar and "menu" means Walker; both still map to `shell_ui` by R1.
