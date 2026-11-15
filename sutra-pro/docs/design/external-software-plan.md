# External software in the Sutra Pro library: plan

Audience: the owner and the team. Kaivan works on the shared library, so the split in section 8 is for him.
Status: design only, written before any implementation. Version context: Sutra Pro 0.4.0. Revised 2026-11-13 after a verification pass.
Marking: "(unverified)" means the research did not confirm the fact on a primary page. Re-check it before it goes into code. "(proposal)" means a number or rule we chose, with no external source behind it.

## 1. Summary

- **Recommendation:** add an external software catalogue. It is a closed, versioned, owner-approved list of outside software (MCP connectors, Python libraries, CLI tools, skills) with enough metadata to decide whether to use each entry, and rules for how a team's agent may use it.
- **Reference first:** the default is a reference entry, not copied code. Vendoring is rare and needs a permissive licence with its LICENSE file. Installing is an owner action, never an agent action.
- **Agents propose, code validates:** an agent or a discovery job can propose an entry. Only the write gate (`GATE.check`) can admit it, and only after code-run checks. The owner approves what enters the catalogue and what a team may enable.
- **Trust is computed:** the trust level comes from checks code runs. It is never a model opinion and never a field a proposer fills in. The level names and thresholds in 4.2 are a proposal, not a finding.
- **Network is owner-triggered:** discovery is local-first. The owner clicks "refresh", Sutra syncs to a local file or SQLite table under the data folder, and matching is then offline. No API key is stored anywhere.
- **Where it lives:** a separate catalogue from the template library (reusable section specs). The two share the word "library" but not the store. The catalogue is mostly Sutra Pro app work. Kaivan's shared library work gets the record shape and the gate rules, as far as the context shows (section 8).
- **Shortlist:** 22 candidates in section 7. The proposed first wave is small and read-only: Filesystem, Git, Fetch, MarkItDown, GitHub (official), Playwright MCP and the MCP Python SDK. DuckDB joins only after its wheel check passes (see section 7).
- **Registry caveat:** the official MCP Registry's own about page says it is in preview and is meant for downstream aggregators, and that host apps should not consume it directly. Sutra is a host app, so direct sync from it is not settled. Phase 3 is gated on resolving this (section 3.2, open question 1).
- **macOS caveat:** no verified, supported per-process sandbox was found for macOS, but the one Apple page consulted returned no content, so this is absence of evidence, not a finding (unverified). Version 1 should record declared access, ask for explicit consent, and not claim enforcement there.

## 2. What "external software in the library" means

### 2.1 Kinds

| Kind | What it is | Typical launch | Main concern |
|---|---|---|---|
| `mcp_connector` | An MCP server an agent can call (stdio or remote HTTP) | Subprocess over stdio, or a remote URL | Tool poisoning, rug pull, tool output as prompt injection; for remote servers also authorization (see 6.2) |
| `python_library` | A pip package imported in a process | `uv pip install` of a pinned wheel | Transitive licences, wheels for macOS and Windows, deserialisation |
| `cli_tool` | A command-line program a connector or run shells out to | Subprocess with the env allowlist | Arbitrary code, file and network reach |
| `skill` | A prompt and instruction bundle (for example from a plugin marketplace) | Read as text, never executed | Hidden instructions in text |
| `template` | A section spec for an artifact, from outside | Imported through the template library's existing rules | Already covered by the closed Template classes |

Out of scope for v1: services that need a daemon (Penpot, Neo4j and similar). They can be listed as `reference_only` with the note "owner installs separately".

### 2.2 Reference, vendored, installed

| Mode | Meaning | Who may do it | Condition |
|---|---|---|---|
| Reference | The entry points at the source, with metadata. Nothing is fetched or run. | Code, after the gate admits the record | Any licence may be referenced, but the record must say what it is |
| Vendored | The source is copied into the repo under the read-only vendoring pattern, with a LICENSE file beside it and a sha256 table | Developers, through `scripts/vendor_j2.py`-style tooling | Permissive OSI licence only (MIT, Apache-2.0, BSD, ISC), as `d3-LICENSE` does today |
| Installed | The software is fetched and made runnable in the data folder | Owner only | Pinned version and digest, no install scripts run, per-team enablement afterwards |

A weak-copyleft (MPL-2.0) or fair-code tool is never vendored. The owner may run it as a separate program.

## 3. Discovery

### 3.1 The rule

Agents propose, code validates. A proposal, from an agent or from a discovery sync, is a draft record. It enters the catalogue only through `GATE.check` into a registered closed family, with the code-run checks of section 4.3 attached. A model never writes to the catalogue store directly, and a model never sets `trust_level`.

### 3.2 Sources, by role

Confirmed on a primary page unless marked.

| Role | Source | Use | Notes |
|---|---|---|---|
| Discover | Official MCP Registry | Find MCP connectors | **Confirmed (about page):** preview status ("breaking changes or data resets may occur"); reverse-DNS namespace verification (GitHub, DNS, HTTP); security scanning is delegated to package registries; intended consumers are aggregators pulling regular but infrequent (about hourly); host apps are told not to consume it directly. **Unverified:** endpoint path (`/v0.1/servers`), `updated_since`, `version=latest`, cursor paging, substring-only search, sort by version string, absence of a licence field, API freeze date, and the data licence. The docs page fetched returned only a title. Read `docs/reference/api/openapi.yaml` and the aggregator guide before any code. |
| Discover | npm search `/-/v1/search` | Find Node-based connectors by keyword | (unverified, not re-opened) Result has no licence; a second request per package is needed. Reference only, since Sutra has no Node install. |
| Discover | GitHub topic and repository search | Find candidates in no registry | Unauthenticated limit is 10 requests per minute. At most 1,000 results per query, 100 per page. Topics are noisy. |
| Vet | GitHub repository object | `license.spdx_id`, `archived`, `pushed_at` | `license` can be null or NOASSERTION. |
| Vet | PyPI JSON API | `license_expression` (in `info`), `vulnerabilities` (top-level), file list | Use the per-version endpoint `/pypi/<project>/<version>/json`. The project endpoint's `vulnerabilities` reflects the latest release only, and its `releases` key is deprecated (use the Index API for wheel lists). `license_expression` is often null (duckdb's is null, with the licence only in a classifier). No search endpoint in the docs. Covers PyPI packages only. |
| Vet (proposed, not yet researched) | OSV.dev and GitHub Advisory Database | Advisories for PyPI, npm, Go and git sources | PyPI's field alone leaves npm and Go-binary servers with no advisory source. Confirm API terms before use. |
| Vet (proposed, not yet researched) | deps.dev, OpenSSF Scorecard | Transitive dependency and licence data; maintenance signals | Needed for `transitive_licenses_checked: full`; no source is named otherwise. Confirm terms and Windows-friendliness (plain HTTPS needs no install). |
| Leads only | Awesome lists, `marketplace.json` files, n8n community nodes | Names to feed into the vetting step | (unverified) No licence or security data. Awesome lists have no API. A marketplace has no central index, so the owner names each one. n8n nodes need the n8n runtime. |
| Models | Hugging Face Hub API | Local embedding model candidates, if ever needed | Model licences are separate from code licences. Endpoint details unverified. |

### 3.3 How and how often

- **How:** a plain HTTPS JSON client in the Sutra server, never in the engine process. It runs only when the owner presses "refresh sources". Responses are parsed tolerantly into closed models (library principle DL4). Each source is synced to a local table or JSON file under the data folder, then matched offline with FTS5.
- **Registry stance:** until open question 1 is answered, treat the MCP Registry as one of three options: (a) owner-triggered pull of a small filtered slice, if the docs permit it for a single-user app; (b) hand-written entries only; (c) a pull through an aggregator. Do not build the sync before this is settled.
- **How often:** manual by default. The owner can set a reminder, but there is no background polling, because the product pushes nothing anywhere unless asked. Re-verification of existing entries (section 4.3) is also manual, with a "stale after N days" flag shown in the UI.
- **Tests:** the default suite makes no network call. It uses recorded fixtures of each source's response.
- **Rate limits:** GitHub unauthenticated lookups are slow by design. The sync fetches only candidates that pass the cheap registry filters first.
- **Data terms:** storing third-party registry listings locally raises licence and attribution questions (open question 1). Record source and fetch date on every synced row.

### 3.4 Who approves what

| Step | Actor | Gate |
|---|---|---|
| Find a candidate | Agent or sync job | None, it is a draft |
| Build the record, run checks | Code | Closed model, SPDX parse, digest, tool-list hash |
| Admit to the catalogue | Code via `GATE.check`, plus owner click | Licence policy is allow or review, no hard-deny check failed |
| Install | Owner only | Risk prompt, exact launch command shown in full |
| Enable for a team | Owner (or a team lead the owner delegates, see Decision D) | Per-team list |
| Use inside a run | The team's agent | Only enabled entries, only declared access |

## 4. The metadata record

One closed, strict, versioned family in the Interface library (`extra=forbid`, canonical JSON plus sha256, exported schema, drift test). The name is a proposal: `external_software/1`. Fields depending on unverified registry data (`registry_name`, anything mapped from `server.json`) may change once open question 2 is answered.

### 4.1 Field list

| Field | Type | Set by | Notes |
|---|---|---|---|
| `id` | slug string | Code | `^[a-z][a-z0-9._-]{1,59}$`, no control or bidi characters, reserved and impersonation names refused, Windows device names avoided |
| `schema` | literal `"external_software/1"` | Code | |
| `name` | string, max 80 | Proposer | Display name |
| `summary` | string, max 300 | Proposer | Scrubbed, no secret shapes |
| `kind` | enum: `mcp_connector`, `python_library`, `cli_tool`, `skill`, `template` | Proposer, checked | |
| `mode` | enum: `reference`, `vendored`, `installed` | Code from owner action | Reference by default |
| `source_url` | https URL | Proposer, checked | Host allowlist per source type |
| `source_type` | enum: `mcp_registry`, `github`, `pypi`, `npm`, `marketplace`, `manual` | Code | |
| `registry_name` | string or null | Code | For example the MCP registry namespaced id |
| `version` | string | Code | Exact pinned version. No `latest`, no branch. |
| `commit_sha` | 40 hex or null | Code | For git sources |
| `digest` | `sha256:<hex>` or null | Code | Of the archive or wheel actually used. Required for `installed` and `vendored`. |
| `license_spdx` | string | Code | SPDX expression, parsed per clause and validated against a bundled copy of the SPDX list (shipped with its licence file). A mixed-licence repo is written as an expression (for example `Apache-2.0 AND MIT`) taken from the LICENSE file of the specific package and version, never copied from the repo root |
| `license_source` | enum: `github_api`, `pypi_metadata`, `license_file`, `manual` | Code | Where the licence claim came from |
| `license_policy` | enum: `allow`, `review`, `deny` | Code | Computed from `license_spdx`. NOASSERTION and `LicenseRef-*` map to `review`. |
| `transitive_licenses_checked` | enum: `no`, `partial`, `full` | Code | Needs a dependency-tree source (see 3.2) |
| `capabilities` | list of enum | Proposer, checked | For example `read_files`, `web_fetch`, `code_hosting`, `browser` |
| `tools` | list of {name, read_only} | Code | From the first tool listing at approval |
| `tool_list_hash` | `sha256:<hex>` or null | Code | Hash of tool names, descriptions and input schemas at approval (rug-pull defence) |
| `permissions_needed` | list of enum | Proposer, checked | For example `fs_read`, `fs_write`, `net_out`, `spawn_process`, `oauth_scope:<x>` |
| `file_access` | {paths: list, write: bool} | Owner on enable | Declared scope, for example the team's working folder |
| `network_access` | {hosts: list, local_only: bool} | Proposer, checked | Declared hosts. "Declared" is not "enforced" on macOS. |
| `enforcement` | enum: `declared_only`, `enforced` | Code per OS | See section 6.3 |
| `secrets_needed` | list of env var names (names only) | Proposer, checked | Never values. Names must be Redactor-covered. |
| `returns_untrusted_content` | bool | Proposer, checked | True for web, mail, files, issue trackers |
| `launch` | {command, args, transport} | Code | Shown in full to the owner before first run. Flagged patterns include `sudo`, `rm -rf`, shell pipes. Launchers such as `uvx` and `npx` need a runtime Sutra may not bundle (see 6.4 and open question 6) |
| `provenance` | {kind, signer_identity, source_repo, verified_at} or null | Code | npm provenance, PyPI attestation (PEP 740; identities are GitHub Actions, GitLab CI/CD, Google Cloud), Sigstore. Absence lowers trust but does not block. |
| `maintenance` | {last_release, archived, pushed_at} | Code | From the GitHub and registry lookups |
| `known_advisories` | list of {id, fixed_in} | Code | From PyPI, OSV or GitHub advisories, and the owner's notes |
| `trust_level` | enum: `blocked`, `unreviewed`, `basic`, `reviewed`, `trusted` | Code only | Section 4.2 |
| `trust_inputs` | list of {check, result, at} | Code | The evidence behind `trust_level` |
| `last_verified` | ISO date | Code | |
| `owner` | string | Code | The catalogue steward for this entry (a person or team id), not the upstream author |
| `enabled_for` | list of org-chart NodeIds, or `["*"]` for org-wide | Owner | Keys on chart NodeIds so it survives merge and move (carry_links, aliases) |
| `proposed_by` | {who, function, run_id, at} | Code | Who wrote it: owner, agent function, or system. |
| `mock` | bool | Code | Mock or test entries never reach a live run |
| `expires` | ISO date or null | Owner | Same idea as owner-note expiry |

### 4.2 How trust is computed

Code only, from the checks. A model can never raise the level. The five levels, the 90-day window and the "drop one level" rule are a design proposal with no external source. They should be tuned after Phase 2 shows what owners actually find usable.

- `blocked`: licence policy is `deny`, or the entry is on the local block list, or a hard check failed (digest mismatch, tool list hash changed and not re-approved, archived upstream with a known unfixed advisory).
- `unreviewed`: a draft. Reference only. It cannot be installed or enabled.
- `basic`: licence policy `allow`, pinned version and digest recorded, tool list captured, no `blocked` condition.
- `reviewed`: `basic` plus the owner has read the full launch command and tool descriptions and clicked approve, plus provenance present or an owner note explaining its absence.
- `trusted`: `reviewed` plus a recent verification (default under 90 days, proposal), no known open advisory against the pinned version, and transitive licences checked `full`.

A change that adds a dependency, adds a tool, or changes a tool description drops the entry one level and requires re-approval (proposal). The motivation is that supply-chain compromises tend to arrive in an update or a dependency edge rather than at first review. The GlassWorm case behind this rests on one press article and is illustrative only.

### 4.3 Checks code runs

Licence parse and policy, SPDX list membership, digest compute and compare, wheel availability for macOS arm64, macOS x64 and Windows x64 on Python 3.11 (PyPI per-version file list), pinned requirements, tool-list capture and hash, description scan for hidden characters and instruction-like text (heuristic, bypassable, so one input among several), launch-command flag scan, archived and last-push check, advisory lookup (PyPI plus OSV or GitHub advisories). Network checks run in an owner-triggered refresh and are stored with their date.

### 4.4 Example entry

```json
{
  "schema": "external_software/1",
  "id": "mcp-git",
  "name": "MCP Git server",
  "summary": "Read, search and manipulate local Git repositories over stdio.",
  "kind": "mcp_connector",
  "mode": "reference",
  "source_url": "https://github.com/modelcontextprotocol/servers",
  "source_type": "github",
  "registry_name": null,
  "version": "2026.11.11",
  "commit_sha": null,
  "digest": null,
  "license_spdx": "MIT",
  "license_source": "pypi_metadata",
  "license_policy": "allow",
  "transitive_licenses_checked": "no",
  "capabilities": ["code_hosting", "read_files"],
  "tools": [{"name": "git_status", "read_only": true}, {"name": "git_commit", "read_only": false}],
  "tool_list_hash": null,
  "permissions_needed": ["fs_read", "spawn_process"],
  "file_access": {"paths": [], "write": false},
  "network_access": {"hosts": [], "local_only": true},
  "enforcement": "declared_only",
  "secrets_needed": [],
  "returns_untrusted_content": true,
  "launch": {"command": "uvx", "args": ["mcp-server-git==2026.11.11"], "transport": "stdio"},
  "provenance": null,
  "maintenance": {"last_release": null, "archived": false, "pushed_at": null},
  "known_advisories": [],
  "trust_level": "unreviewed",
  "trust_inputs": [{"check": "license_policy", "result": "allow", "at": "2026-11-13"}],
  "last_verified": "2026-11-13",
  "owner": "library-steward",
  "enabled_for": [],
  "proposed_by": {"who": "system", "function": null, "run_id": null, "at": "2026-11-13"},
  "mock": false,
  "expires": null
}
```

Basis for the example: PyPI JSON for `mcp-server-git` showed latest 2026.11.11, licence MIT, and an empty `vulnerabilities` list. An earlier draft listed CVE-2025-68143 fixed in 2026.1.14 from search-result summaries. That could not be confirmed on a primary page, so it is removed. Before the entry is used, read the GitHub security advisories for the repo and fill `known_advisories` from them. The `mcp-git` PyPI package is published from the monorepo; the monorepo root has mixed licensing, so `license_spdx` comes from the package's own metadata. `null` fields are filled by the first owner-triggered verification.

## 5. Reuse expectations

| Topic | Expectation |
|---|---|
| Install | Owner only. Uses the pinned version and digest. Install and lifecycle scripts never run. Python libraries come in as wheels via `uv`. Everything lands under the data folder. (The Shai-Hulud and Claude Code npm-source lessons behind the no-scripts rule are from secondary sources.) |
| Pin | Exact version, 40-char sha for git sources, sha256 for archives. A floating ref is refused at the gate. One source of truth for the version (avoid the plugin.json-versus-entry drift seen in Claude Code marketplaces). Pin the current verified release, not a floor taken from a search snippet. |
| Update | Explicit owner action. Shows a diff of version, digest, tools, dependencies and licence. Any change to licence, tool list or dependencies drops trust one level until re-approved. A downgrade is uninstall plus reinstall at a pinned version. |
| Uninstall | Removes the install and its data, keeps an audit row, keeps a renames map so old ids still resolve. |
| Offline | The catalogue is a local file or SQLite table, so reading it needs no network. Installed items run offline unless they declare `net_out`. A failed or timed-out lookup returns fewer or no entries and never fails a run (same posture as `LibraryBusy`). |
| Per-team enablement | `enabled_for` holds org-chart NodeIds, plus an explicit org-wide value. A team never sees another team's enablement. Re-pointed through carry_links and aliases on a merge, move or archive, and cleaned on department deletion. |
| What a team's agent may do | Call only tools of enabled entries, within the entry's declared file and network scope, with write tools behind an approval flag (default off). It may propose a new entry. It may not install, enable, widen scope, or edit a record. |
| Scrubbing and egress | Every prompt that carries tool input or output passes the egress scrub and the Redactor. Secrets are passed as env names expanded at launch, only to the one process that needs them. CLI children get the existing env allowlist (no `SUTRA_*` or `J2_*`). Credential-named variables are never placed in remote URLs or headers. |
| Tool output | Wrapped and labelled as untrusted data. It never triggers a write by itself. Any write that follows goes through `GATE.check`. |
| Audit trail | Each install, update, enable, disable, approval, and each tool call by a team's agent writes an Atom log entry (append-only, one open atom per node). Payloads are not stored, as with the egress audit row. |
| Cost | Catalogue use makes no model call of its own. A connector's own cost (hosted APIs, tokens, time) is a field the owner sees at enable time (`cost_note`, a possible later addition). Model work still goes through the owner's own CLI logins only. A connector that needs a hosted-model key is `reference_only`. |

## 6. Trust and safety

### 6.1 Supply chain

- Provenance and signatures (Sigstore, npm provenance, PyPI attestations per PEP 740) show who built an artifact from what source. PyPI attestations are confirmed to bind a file digest to a signing identity; they do not prove safety, and npm's own docs say the same of provenance. They are inputs to the trust level, and absence lowers the level without blocking.
- Never run install scripts. Hold no publish tokens. Pin by digest. (Shai-Hulud lessons, secondary sources only, counts differ by source and are unverified.)
- Transitive dependencies matter: a licence scan and an advisory lookup over the full tree are needed before `trusted`. First-wave examples with large trees: MarkItDown's optional extras and the MCP Python SDK's dependencies, neither scanned yet. SBOM (CycloneDX) is optional input where a project ships one.
- Deserialisation is a code-execution path (the LangChain FAISS and `load()` advisories, seen as search snippets only, unverified). A reference to a package that loads pickles or serialised objects carries a warning, and Sutra never auto-loads such objects.
- Typosquatting and trojaned servers: names are checked against reserved and look-alike rules, and the MCP registry's reverse-DNS namespace verification is a cheap identity signal. Precedent for fake or trojaned MCP packages on npm or PyPI was not researched (gap).

### 6.2 Prompt injection and MCP-specific risks

- Tool output from a connector that reads the web, mail, files or issues is an indirect injection channel. OWASP states no mitigation is foolproof.
- Controls in code: label as untrusted, scrub egress, least privilege, read-only default, no auto-write, human approval for high-risk actions, adversarial tests with planted instructions.
- Rug pull and shadowing: MCP servers can change their tool list after approval (`listChanged`), and annotations are untrusted by spec. So pin `tool_list_hash`, compare on every connect, require re-approval on change, and keep connectors isolated so one connector's descriptions cannot steer another's tools.
- The research found that non-interactive CLI runs can load project MCP servers without asking (unverified). Sutra must not spawn CLIs with unreviewed project MCP config.
- Remote HTTP connectors (gap, not researched): the MCP authorization model (OAuth 2.1), token passthrough and confused-deputy risks are not covered by the stdio controls above. v1 should treat remote connectors as reference only until the MCP security best-practices page and the authorization spec are read.

### 6.3 Sandboxing

| OS | Primitive | Status |
|---|---|---|
| Windows | AppContainer (separate identity, file and registry access only where granted, per-class network). Page dated 2025-07. | A candidate least-privilege primitive, not yet a plan of record. API details and compatibility with Node and Python servers not verified (open question 5). A launcher behind one `oslayer.py` function is the idea, to be proven by a spike. |
| macOS | App Sandbox requires entitlements and may not fit an unsigned Python server launching arbitrary downloaded processes. `sandbox-exec` may be deprecated. | The Apple page returned no content, so all of this is unverified, and "no supported sandbox exists" is not a finding. |

Consequence: the record carries `enforcement` (`declared_only` or `enforced`). On macOS v1, access is declared, consent is explicit, the working folder is the only path offered, and the UI says "not enforced on this system". This is a cautious default chosen because nothing was verified, and it is revisited after a research spike. Docker is not an option for bundling (no extra daemon, and heavy on Windows). Note that some candidates (postgres-mcp, GitHub MCP) offer Docker only as an alternative to a native build, so the rule applies to bundling, not to what an owner may do separately.

### 6.4 Review gates

1. Gate admission (code): closed record, licence policy, no hard-deny check.
2. Owner approval to install: shows the full launch command untruncated, the full tool descriptions, declared access, secrets needed, trust inputs.
3. Per-team enablement (owner): scope and write-tool switch.
4. Re-approval on change: version, tool list hash, dependencies, licence.
5. Local block list (owner-editable) that disables and uninstalls matching entries.
6. First-use confirmation for any tool flagged write or `spawn_process`.

Launch prerequisites (gap): example entries launch with `uvx`, and many MCP servers need `npx`. No decision exists on bundling `uv` or Node for Windows and macOS owners. Until it does, entries needing an unbundled runtime stay reference-only (open question 6).

## 7. The candidate shortlist

Licences are as seen on repository pages unless marked. Verification state is in the last column of notes: "confirmed" means re-opened on a primary page in the verification pass; "unconfirmed" means it rests on earlier research summaries that were not re-opened. Stars and release dates are not given, so no maturity claim is made for any row.

Licence note for rows 3, 6, 9, 20: the `modelcontextprotocol/servers` README says new contributions are Apache-2.0 and existing code stays MIT. That is a mixed repo licence, not a per-server dual licence. Record the licence per server and per version from that package's LICENSE file.

| # | Group | Candidate | Kind | Licence | Reason to include | Risk | State |
|---|---|---|---|---|---|---|---|
| 1 | Plumbing | MCP Python SDK | python_library | MIT | Official way to host a stdio MCP client. Python 3.11+, matches Sutra | Adds a dependency, transitive licences not scanned | unconfirmed beyond licence |
| 2 | Plumbing | FastMCP | python_library | Apache-2.0 | Optional, for writing thin in-house connectors | Another dependency, Python support unverified. Defer. | unconfirmed |
| 3 | Files and docs | MCP Filesystem server | mcp_connector | MIT and Apache-2.0 by file (see note) | Scoped file access, a model for Sutra's own scoped tool | Reference-grade, needs Node, directory-bypass is the user's deployment problem | still an active reference server (confirmed) |
| 4 | Files and docs | Microsoft MarkItDown | python_library | MIT (confirmed) | Converts PDF, Word, PowerPoint, Excel and more to Markdown | Runs with process privileges. The README does not state offline operation outright; it is implied by `convert_local()` and optional dependencies. Hosted paths exist: LLM image captioning, speech transcription, Azure Document Intelligence and Content Understanding, YouTube transcripts, and the markitdown-ocr plugin (sends images to a vision model). All must stay off, with a test that the first wave makes no network call | confirmed |
| 5 | Files and docs | pypdf | python_library | BSD-3-Clause (confirmed from LICENSE file on main) | Pure-Python PDF text, easy on both OSes | Basic extraction | confirmed |
| 6 | Web | MCP Fetch server | mcp_connector | see note | Cheapest web-read connector, no key | SSRF toward localhost or LAN, injection from page content | still active (confirmed) |
| 7 | Web | Trafilatura | python_library | Apache-2.0 from 1.8.0; earlier versions GPLv3+ (confirmed) | Cleans pages before they enter a prompt, works offline on saved HTML | Must pin 1.8.0 or newer | confirmed |
| 8 | Web | Brave Search MCP | mcp_connector | MIT | Search connector from the vendor | Needs `BRAVE_API_KEY` and network. Opt-in only, owner decision needed | unconfirmed |
| 9 | Code and git | MCP Git server | mcp_connector | MIT (PyPI, latest 2026.11.11) | Local, keyless, useful to code teams | Advisories: an earlier draft cited four CVEs and a 2026.1.14 floor from search summaries; PyPI shows none. Unconfirmed either way. Read the GitHub security advisories, pin the current release, read-only use | licence confirmed; advisories unverified |
| 10 | Code and git | GitHub MCP server (official, `github/github-mcp-server`) | mcp_connector | MIT (confirmed) | Strongest code-hosting connector, has `--read-only` (write tools skipped even if requested) and `--toolsets`. Go build plus a ghcr.io Docker image | Needs a token (the page was read only in part, so the requirement and required scopes are unverified). Use the Go binary rather than Docker on Windows. Do not confuse with the archived reference GitHub server | mostly confirmed |
| 11 | Email and calendar | workspace-mcp (Google Workspace) | mcp_connector | MIT | One connector for mail, calendar, files | Large write surface, owner must create an OAuth client, community-maintained | unconfirmed |
| 12 | Chat | Slack MCP (korotovsky) | mcp_connector | MIT | Read-focused, posting off by default | Stealth mode uses browser session tokens, terms status unclear. Reference only until a policy decision | unconfirmed |
| 13 | Design | Figma-Context-MCP (Framelink) | mcp_connector | MIT | Gives agents Figma layout data for design and website types | Needs a Figma token (pass by env), hosted service, needs Node | unconfirmed |
| 14 | Design | Penpot (with MCP) | cli_tool / service | MPL-2.0 | Only self-hostable design option found | Weak copyleft, needs Docker or a server. Reference only, never vendored | unconfirmed |
| 15 | Databases | postgres-mcp (crystaldba) | mcp_connector | MIT (confirmed) | Restricted mode gives read-only transactions with a time cap | README says "Docker or Python 3.12 or higher", so run as a separate `uvx` process. A third-party replacement for the archived reference Postgres server; its maintenance record was not checked | mostly confirmed |
| 16 | Data | DuckDB | python_library | MIT (PyPI `license_expression` is null; MIT is in a classifier) | Embedded analytics over CSV, Parquet, JSON, no daemon | Latest is 2.0.0 but its file list was not seen. Older releases have cp311 win_amd64 and macOS arm64 wheels. Needs read-only connection. **Not first wave until the 2.0.0 wheel check (4.3) passes** | licence confirmed; wheels unverified |
| 17 | Browser | Playwright MCP | mcp_connector | Apache-2.0 (confirmed) | Best-supported browser connector, local | README: "not a security boundary" (origin lists and file guardrail are conveniences). `browser_run_code_unsafe` is RCE-equivalent and must stay off. Browsers are headed by default, so the launcher must pass `--headless`. Browser download needs the owner's say | confirmed |
| 18 | Browser | Stagehand | python_library / cli_tool | MIT | Local CLI needs no key | SDK needs a model key, overlaps Playwright. Second choice | unconfirmed |
| 19 | Browser | browser-use | python_library | MIT | Same Python version, can use local endpoints | Defaults to hosted gateway and keys, runs its own agent loop and so bypasses "code validates". Reference only | unconfirmed |
| 20 | Memory | MCP Memory server | mcp_connector | see note | Worked example of an agent memory tool | Model writes straight to the store. Reference only | still active (confirmed) |
| 21 | Memory | sqlite-vec | python_library | Apache-2.0 / MIT | Fits one-file SQLite | Pre-v1, needs an embedding model, FTS5 is enough today. Defer | unconfirmed |
| 22 | Memory | Mem0 and Graphiti | python_library | Apache-2.0 | Ideas for memory design | Default to hosted keys or a graph server, model writes directly. Reference only (one row, two projects) | unconfirmed |

Excluded or unverified: SearXNG (AGPL) and pandoc (GPL) were excluded from memory without opening their licences. They are probably right, but unverified. IMAP, Discord, Notion, Zapier, and Go or Rust binaries with published checksums and signatures were not researched. Archived reference servers: GitHub, Slack, PostgreSQL, Puppeteer and SQLite are confirmed archived on the servers repository README (moved to `servers-archived`). Redis, Sentry and Google Drive were not seen on that page and are unconfirmed. Do not recommend any of them.

Standards used as inputs, not candidates: SPDX list, Sigstore, CycloneDX, SLSA. OpenSSF Scorecard and deps.dev are listed as possible data sources in 3.2 (not yet researched). A verifier library would need its own licence and Windows-wheel check before use (unverified).

## 8. Phased plan

Sizes: S is about a day, M is about a week, L is two to three weeks. These are estimates, not commitments.

### Ownership split

The context shows the template library is a vendored J2 engine module (`j2_template_lib.py`, byte-identical except numbered patches) plus closed classes in `sutra_app/library/templates.py`. Nothing in the context shows the external catalogue touching the vendored text. So, as far as the context shows:

| Belongs to the Sutra Pro app | Belongs to the shared J2 library (Kaivan) |
|---|---|
| Registered record family and its gate rules, schema export, drift test (`sutra_app/library/`) | Whether `template` as a kind of external entry should reuse the existing Template classes and `route()` matching |
| Source clients, the local cache, FTS5 matching, check runners | Any change to `j2_template_lib.py` itself, which must go through a numbered patch in `VENDORED.md` and stays out of v1 |
| Owner UI: approve, install, enable, block list, "refresh sources" | The shared vocabulary for `capabilities` and `permissions_needed`, if the J2 side also needs it (open question) |
| Per-team enablement keyed on chart NodeIds, carry_links handling | Seed content: starter entries synced like the seed library (marker file, `config sync-library` style) |
| Launcher, env allowlist, sandbox wrapper in `oslayer.py` | |
| Atom log entries, egress scrub on tool I/O, backup inclusion | |

Where the line falls for the shared library is a question for Kaivan (Decision C).

### Phases

| Phase | Content | Size | Owner |
|---|---|---|---|
| 0 | Decide D, A, B below. Confirm the SPDX list copy and its licence. Read the MCP Registry OpenAPI spec and aggregator guide (open questions 1, 2). Draft the record family. | S | Owner, Kaivan |
| 1 | Record family `external_software/1`, gate rules, licence policy function (including mixed-licence expressions), schema export and drift test, fixtures. No network, no install. | M | App (record), Kaivan reviews shape |
| 2 | Reference-only catalogue: local file or SQLite store, FTS5 search, read-only UI list, 7 starter entries from the first-wave shortlist (DuckDB added when its wheel check passes), hand-written and hand-checked against primary pages, with advisories read from GitHub or OSV. Audit rows in the Atom log. | M | App |
| 3 | Discovery: owner-triggered sync, only after Phase 0 settles whether the MCP Registry may be consumed directly. GitHub and PyPI (per-version endpoint) vetting, advisory source, recorded fixtures, tolerant parsers, stale flags. | L | App |
| 4 | Install and pin: digest check, no scripts, install into the data folder, uninstall, update diff, block list, backup and wipe round trip. Decide uv and Node bundling first. | L | App |
| 5 | Run integration: MCP launcher over the MCP Python SDK, per-team enablement, untrusted-output labelling, tool-list hash and re-approval, write-tool approval flag. | L | App |
| 6 | Sandbox: spike on Windows AppContainer behind `oslayer.py` and on macOS options, then decide. | L, risky | App |

### Build first

Phase 1 and 2 only: the closed record, the gate, the licence policy, a read-only local catalogue with a handful of hand-checked entries. It delivers value (a vetted list) and proves the record shape before any code that fetches or runs outside software.

### Do not build (yet)

- No auto-install and no agent-initiated install.
- No background polling or auto-update.
- No vendoring pipeline for third-party code beyond the existing pattern.
- No hosted-key connectors in the default catalogue.
- No in-process Node or n8n runtime.
- No vector index or embeddings for catalogue search (FTS5 is enough).
- No copying of Claude Code's `command` source type, and no plugin hooks.
- No claim of macOS sandboxing.
- No direct MCP Registry sync until its docs are read and permit it.

## 9. Risks, open questions, decision candidates

### Risks

- Each source is incomplete: the PyPI `license_expression` is often null, npm search results are reported to lack a licence (unverified), and the MCP Registry licence field is unconfirmed. Licence trust therefore rests on our own checks.
- The MCP Registry is in preview ("breaking changes or data resets may occur"), and says host apps should not consume it directly. Parsers must be tolerant, and the sync design may need to change.
- Advisory coverage is thin: PyPI covers only PyPI packages and the latest release at the project endpoint. npm and Go-binary servers need another source (OSV, GitHub advisories).
- A malicious change arriving by update or dependency edge. Mitigation is re-approval on change.
- Declared access is not enforced on macOS, so a consenting owner can still be harmed.
- Several research fetches were summarised by a model, so quoted field details need rechecking against the pages before they go into code. Rows marked "unconfirmed" in section 7 are in this state.
- Python 3.11 and Windows wheel gaps (DuckDB, others) can remove a candidate late.
- Owner effort: approvals can become a chore, which is a pressure to weaken the gates.
- Data terms: storing third-party registry listings locally may carry licence or attribution duties (unverified).
- Mismatch noted by the research: parts of the supplied context were memory-store criteria rather than discovery criteria. This plan applies only the constraints that carry over (local-first, keyless, permissive licence, closed models, owner-triggered network).

### Open questions

1. May Sutra, as a host app, pull from the MCP Registry, and does the registry data have a stated licence for redistribution of listings? The about page says host apps should not consume it directly. (blocks Phase 3)
2. What is the actual `server.json` field list and API shape (OpenAPI spec), and does it map cleanly to section 4? (blocks Phase 3)
3. Is there a supported macOS per-process sandbox that fits an unsigned Python app? (unverified, Apple page returned nothing)
4. Are Sigstore and `npm audit signatures` usable offline with a cached trust root? Windows wheels for a Python Sigstore verifier? (unverified)
5. Does Windows AppContainer work with Node and Python MCP servers in practice? (unverified)
6. Does a Node requirement for most MCP servers, and the need for `uv` or `npx`, fit "no compile step, Python only" for the owner's install? Reference-only may be the honest answer for those.
7. Should `template` external entries reuse the template library's matching, or stay a plain catalogue row?
8. Does a search or Figma token count as a "key" under the rule that no API key is stored? The env-name-only design avoids storing values, but the rule's intent needs the owner's reading.
9. Which advisory and transitive-dependency sources (OSV, GitHub advisories, deps.dev, Scorecard) are acceptable on terms and offline posture?
10. What are the real GitHub MCP token scopes, and can a fine-grained token enforce read-only independently of the `--read-only` flag?

### Decision candidates

- **Decision A: default mode.** Reference-only for all external software until Phase 4, with install as an owner-only action afterwards. Alternative: allow install of read-only, pinned, permissive entries from Phase 2. Recommended: reference-only first.
- **Decision B: network use.** Discovery and verification only on an explicit owner action, with local cache and recorded fixtures for tests. Alternative: a scheduled refresh. Recommended: owner-triggered only, in line with local-first.
- **Decision C: where the catalogue lives.** A separate catalogue in the Sutra Pro app (Interface library family plus its own store), leaving the vendored template library untouched. Alternative: extend the shared J2 library, which needs a numbered patch and Kaivan's agreement on shape. Recommended: separate catalogue, with Kaivan reviewing the record and the shared vocabulary.
- **Decision D: who may enable per team.** Owner only in v1, or owner plus a delegated team lead. Recommended: owner only until the audit trail is proven.
- **Decision E: licence policy.** Permissive only (MIT, Apache-2.0, BSD, ISC) may be vendored or recommended as embeddable. MPL-2.0 and similar may be listed as `reference_only`, run as a separate program. GPL, AGPL, SSPL, BUSL and non-commercial are `deny`, including as listed candidates. Mixed-licence repos are judged per package and version. Recommended: as stated.
- **Decision F: hosted-key connectors.** Keep them out of the default catalogue (reference only), with any opt-in (Brave, Figma, GitHub token) needing a named owner decision and Redactor coverage. Recommended: reference only.
- **Decision G: macOS stance.** Ship v1 with declared-only access and visible "not enforced" labelling, and run a sandbox research spike in Phase 6. This is a cautious default taken because nothing was verified, not because a sandbox was shown not to exist. Alternative: block write-capable connectors on macOS until a sandbox exists. Recommended: declared-only plus a read-only default, revisited after the spike.
