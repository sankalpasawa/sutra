#!/usr/bin/env node
/**
 * Sutra Connectors — Slack MCP server  (sutra-slack)
 *
 * Protocol : MCP 2024-11-05 · stdio transport · newline-delimited JSON-RPC 2.0
 * Registered: ~/.claude/settings.json by `sutra connect slack`
 * Auth      : ~/.sutra-connectors/oauth/slack.json (written by connect.sh)
 * Audit     : .enforcement/connector-audit.jsonl  (appended per-call, append-only)
 *
 * Tools exposed (match manifests/slack.yaml capabilities):
 *   sutra_slack_read_channel   — conversations.history  (depth ≥ 1, T1–T4)
 *   sutra_slack_post_message   — chat.postMessage       (depth ≥ 3, T1–T2, confirm first)
 *   sutra_slack_get_user       — users.info             (depth ≥ 1, T1–T4)
 *
 * Policy note: full depth + tier enforcement lives in ConnectorRouter (L1).
 * This server is the L3 MCP transport. It carries policy in tool descriptions
 * (so Claude self-enforces) and blocks on missing credentials.
 */

import { readFileSync, existsSync, appendFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
import { createInterface } from 'node:readline';

// ── Credential loading ────────────────────────────────────────────────────────

const CRED_DIR = join(homedir(), '.sutra-connectors', 'oauth');

function loadCredential() {
  const jsonPath = join(CRED_DIR, 'slack.json');
  if (!existsSync(jsonPath)) return null;
  try {
    const bundle = JSON.parse(readFileSync(jsonPath, 'utf8'));
    if (bundle.type !== 'slack-bot' || !bundle.token) return null;
    return bundle;
  } catch {
    return null;
  }
}

// ── Audit (append-only, best-effort) ─────────────────────────────────────────

const AUDIT_LOG = join(process.cwd(), '.enforcement', 'connector-audit.jsonl');

function auditAppend(event) {
  try {
    const dir = dirname(AUDIT_LOG);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    appendFileSync(AUDIT_LOG, JSON.stringify(event) + '\n');
  } catch {
    // Never crash the server on audit failure — beacon to stderr instead.
    process.stderr.write(`[sutra-slack] audit write failed: ${JSON.stringify(event)}\n`);
  }
}

// ── Slack API ─────────────────────────────────────────────────────────────────

const SLACK_API = 'https://slack.com/api';

async function slackPost(method, token, body, signal) {
  const init = {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  };
  if (signal) init.signal = signal;
  const res = await fetch(`${SLACK_API}/${method}`, init);
  if (!res.ok) throw new Error(`HTTP ${res.status} calling Slack ${method}`);
  const json = await res.json();
  if (!json.ok) throw new Error(`slack ${method}: ${json.error ?? 'unknown_error'}`);
  return json;
}

// ── Tool definitions ──────────────────────────────────────────────────────────

const TOOLS = [
  {
    name: 'sutra_slack_read_channel',
    description:
      'Read recent messages from a Slack channel. ' +
      'Governed by Sutra tier policy — channel access depends on your tier: ' +
      'T1 (Asawa): any channel | T2 (owned cos): scoped channels | T3/T4: #public-* only. ' +
      'Messages are returned oldest-first.',
    inputSchema: {
      type: 'object',
      properties: {
        channel: {
          type: 'string',
          description:
            'Channel name including # (e.g. "#ops", "#general") or Slack channel ID (e.g. "C1234567890").',
        },
        limit: {
          type: 'number',
          description: 'Number of messages to return. Default 20, max 100.',
          default: 20,
        },
      },
      required: ['channel'],
    },
  },
  {
    name: 'sutra_slack_post_message',
    description:
      'Post a message to a Slack channel. ' +
      'WRITE OPERATION — always confirm with the founder before posting. ' +
      'Sutra policy: depth ≥ 3 required; #public-* channels require depth 5 + explicit founder approval. ' +
      'T1 (Asawa) and T2 (owned portfolio) only — T3/T4 blocked by tier policy.',
    inputSchema: {
      type: 'object',
      properties: {
        channel: {
          type: 'string',
          description: 'Channel name including # (e.g. "#ops") or Slack channel ID.',
        },
        text: {
          type: 'string',
          description:
            'Message text. Slack markdown: *bold*, _italic_, `code`, ```block```, <URL|label>.',
        },
        thread_ts: {
          type: 'string',
          description:
            'Timestamp of the parent message to reply in-thread (optional). ' +
            'Format: "1234567890.123456" — copy from the message permalink.',
        },
      },
      required: ['channel', 'text'],
    },
  },
  {
    name: 'sutra_slack_get_user',
    description:
      'Look up a Slack user profile by Slack user ID. ' +
      'Returns name, handle, title, email, and timezone. Available to all tiers (T1–T4).',
    inputSchema: {
      type: 'object',
      properties: {
        user: {
          type: 'string',
          description: 'Slack user ID (e.g. "U1234567890"). Found in message objects as the `user` field.',
        },
      },
      required: ['user'],
    },
  },
];

// ── Tool handler ──────────────────────────────────────────────────────────────

async function handleToolCall(name, args) {
  const ts = Date.now();
  const sessionId = process.env['CLAUDE_SESSION_ID'] ?? 'unknown';
  const auditBase = { ts, connector: 'slack', tool: name, sessionId };

  const cred = loadCredential();
  if (!cred) {
    auditAppend({ ...auditBase, outcome: 'blocked', reason: 'no_credential' });
    return {
      content: [
        {
          type: 'text',
          text:
            'Slack connector not set up.\n\n' +
            'Run in your terminal:\n' +
            '  sutra connect slack\n\n' +
            'Then restart Claude Code — the connector activates on the next session.',
        },
      ],
      isError: true,
    };
  }

  try {
    if (name === 'sutra_slack_read_channel') {
      const limit = Math.min(Number(args.limit ?? 20), 100);
      const data = await slackPost('conversations.history', cred.token, {
        channel: args.channel,
        limit,
      });

      const messages = (data.messages ?? []).reverse().map((m) => {
        const sec = Math.floor(Number(m.ts ?? 0));
        const isoTime = sec
          ? new Date(sec * 1000).toISOString().replace('T', ' ').slice(0, 19) + 'Z'
          : '?';
        return `[${isoTime}] ${m.username ?? m.user ?? 'unknown'}: ${m.text ?? '(no text)'}`;
      });

      const text = messages.length
        ? `${messages.length} message(s) from ${args.channel} (oldest first):\n\n${messages.join('\n')}`
        : `No messages found in ${args.channel}.`;

      auditAppend({ ...auditBase, channel: args.channel, outcome: 'allowed', msg_count: messages.length });
      return { content: [{ type: 'text', text }] };

    } else if (name === 'sutra_slack_post_message') {
      const body = { channel: args.channel, text: args.text };
      if (args.thread_ts) body.thread_ts = args.thread_ts;

      const data = await slackPost('chat.postMessage', cred.token, body);
      const archiveId = (data.ts ?? '').replace('.', '');
      const channelId = data.channel ?? args.channel;
      const url = `https://slack.com/archives/${channelId}/p${archiveId}`;

      auditAppend({ ...auditBase, channel: args.channel, outcome: 'allowed', msg_ts: data.ts });
      return {
        content: [
          {
            type: 'text',
            text: `Message posted to ${args.channel}.\nTimestamp: ${data.ts}\nURL: ${url}`,
          },
        ],
      };

    } else if (name === 'sutra_slack_get_user') {
      const data = await slackPost('users.info', cred.token, { user: args.user });
      const u = data.user ?? {};
      const p = u.profile ?? {};

      const lines = [
        `Name: ${u.real_name ?? u.name ?? args.user}`,
        `Handle: @${u.name ?? '?'}`,
        `ID: ${u.id ?? args.user}`,
        p.title ? `Title: ${p.title}` : null,
        p.email ? `Email: ${p.email}` : null,
        u.tz ? `Timezone: ${u.tz}` : null,
        u.deleted ? `Status: deactivated` : null,
      ].filter(Boolean);

      auditAppend({ ...auditBase, user_id: args.user, outcome: 'allowed' });
      return { content: [{ type: 'text', text: lines.join('\n') }] };

    } else {
      auditAppend({ ...auditBase, outcome: 'error', reason: 'unknown_tool' });
      return {
        content: [{ type: 'text', text: `Unknown tool: ${name}` }],
        isError: true,
      };
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    auditAppend({ ...auditBase, outcome: 'error', error: msg });

    const isAuthError =
      msg.includes('invalid_auth') ||
      msg.includes('token_revoked') ||
      msg.includes('not_authed') ||
      msg.includes('account_inactive');

    const hint = isAuthError
      ? '\n\nToken appears invalid or revoked. Re-run `sutra connect slack` to refresh, then restart Claude Code.'
      : '';

    return {
      content: [{ type: 'text', text: `Slack error: ${msg}${hint}` }],
      isError: true,
    };
  }
}

// ── MCP stdio protocol (JSON-RPC 2.0, newline-delimited) ─────────────────────

function send(msg) {
  process.stdout.write(JSON.stringify(msg) + '\n');
}

async function handleRequest(msg) {
  if (msg.method === 'initialize') {
    send({
      jsonrpc: '2.0',
      id: msg.id,
      result: {
        protocolVersion: '2024-11-05',
        capabilities: { tools: {} },
        serverInfo: { name: 'sutra-slack', version: '1.0.0' },
      },
    });

  } else if (msg.method === 'notifications/initialized') {
    // Notification — no response.

  } else if (msg.method === 'ping') {
    send({ jsonrpc: '2.0', id: msg.id, result: {} });

  } else if (msg.method === 'tools/list') {
    send({ jsonrpc: '2.0', id: msg.id, result: { tools: TOOLS } });

  } else if (msg.method === 'tools/call') {
    const { name, arguments: args } = msg.params ?? {};
    const result = await handleToolCall(name ?? '', args ?? {});
    send({ jsonrpc: '2.0', id: msg.id, result });

  } else if (msg.id !== undefined) {
    send({
      jsonrpc: '2.0',
      id: msg.id,
      error: { code: -32601, message: `Method not found: ${msg.method}` },
    });
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

process.stderr.write('[sutra-slack] MCP server starting (sutra-slack v1.0.0)\n');

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on('line', (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch {
    send({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } });
    return;
  }
  handleRequest(msg).catch((err) => {
    if (msg?.id !== undefined) {
      send({ jsonrpc: '2.0', id: msg.id, error: { code: -32603, message: String(err) } });
    }
  });
});

rl.on('close', () => {
  process.stderr.write('[sutra-slack] MCP server stopped\n');
  process.exit(0);
});
