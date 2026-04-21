# Versioning Policy

Sutra plugin releases follow [SemVer 2.0](https://semver.org/spec/v2.0.0.html) — `MAJOR.MINOR.PATCH`.

## When we bump each segment

### PATCH (`1.3.0` → `1.3.1`)

Backward-compatible fixes. Safe auto-update. Examples:

- Bug fix in a hook or script
- Brand-leak scrub (like v1.2.1)
- Documentation added or corrected
- CHANGELOG catch-up
- New non-invasive file (e.g., PRIVACY.md, VERSIONING.md itself)

### MINOR (`1.3.0` → `1.4.0`)

New functionality, backward-compatible. Auto-update safe but new features may need user action to use. Examples:

- New slash command or skill
- New hook that doesn't block existing behavior
- New `bin/sutra` subcommand
- New opt-in telemetry field added to the existing schema (additive only)
- Transport change that preserves existing commands (e.g., Supabase as additional destination)

### MAJOR (`1.3.0` → `2.0.0`)

Breaking changes. Users may need to take action. Examples:

- Slash command rename or removal (like v1.3.0's `/sutra:sutra-onboard` → `/sutra:onboard` — **this was technically breaking and should have been 2.0.0; see "Exceptions" below**)
- Hook behavior change that affects existing installations (e.g., warn-only → hard-block)
- Schema field removed or renamed in telemetry
- Minimum Claude Code version increase
- Platform drop (e.g., no longer supporting a surface that previously worked)

## Exceptions

**v1.3.0** shipped a slash-command rename while still pre-v2.0 and while the plugin has an extremely small external user base (founder + 9 telemetry opt-ins at time of ship). The rename was documented as BREAKING in the CHANGELOG. Future pre-v2.0 renames will also use MINOR bumps while the user base is <100 active installs; we'll revisit when usage grows.

## Cadence

- **PATCH**: shipped same-day when a real user is affected
- **MINOR**: roughly every 1-2 weeks while actively developed; slower once stable
- **MAJOR**: only when a breaking change is unavoidable, with at least one MINOR of deprecation notice ahead (unless user base is small enough that direct migration is cheaper)

## Auto-update behavior

Claude Code auto-pulls the latest version on session start for public marketplaces like ours (no token needed). Users can:

- Force-update immediately: `claude plugin marketplace update sutra && claude plugin update core@sutra`
- Pin a version: in `.claude/settings.json` add a `sha` or `ref` to the marketplace entry (advanced; see [marketplace source pinning](https://code.claude.com/docs/en/plugin-marketplaces#version-resolution-and-release-channels))
- Opt out of a version: `claude plugin disable core@sutra`, wait for a fix, then re-enable

## Pre-release conventions

Pre-release labels follow SemVer syntax: `2.0.0-beta.1`, `1.4.0-rc.1`. We don't use pre-releases today (user base too small to be worth the overhead). When we do, they'll publish to the same marketplace with `ref`-pinned entries so early-access users opt in explicitly.

## Release channels

A stable/latest split is on the roadmap (see Punch List P3). Until then, `main` IS the stable channel. Every commit to `main` is shippable; we don't ship WIP to users.

## Yanking a version

If a release breaks things we can't patch quickly:

1. Push a PATCH version that reverts the offending change
2. Update CHANGELOG with a "Yanked" note on the bad version
3. Post to GitHub Issues explaining what to do

We do NOT delete git tags or rewrite history; we ship forward.
