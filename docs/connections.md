# Connect to everything

Quinovo does not ship a catalog of hundreds of vendor adapters. It ships a
small set of universal ones, and it treats MCP as the connector.

The workspace page is **Connections** (`/sources`). Two lists: data coming in,
and actions going out.

## Data coming in

Register a named source, map its fields onto an object type, then pull — or
let the autonomy loop pull anything marked auto. Sources live in the local
database under `.data/`, not in the pack.

| Kind | What it does |
|------|----------------|
| Web address (`http`) | GET a JSON list (or a common wrapper) and upsert each row. |
| JSON feed (`json`) | Same idea, tuned for a public array. |
| Spreadsheet (`csv`) | Read a CSV file on this machine. |
| Incoming push (`webhook`) | Other systems `POST /ingest/{name}`. Optional shared token. |
| Database (`sql`) | One read-only query. SQLite always works. Postgres needs an optional driver — if it is missing, the source says so instead of pulling in a heavy dependency. |
| MCP (`mcp`) | Call a listed tool on another MCP/JSON-RPC endpoint (HTTP, or a one-shot stdio command). |
| Demo (`synthetic`) | In-memory rows. For tests and agents. |

A Hermes (or any MCP) agent wires a source by calling `register_source` with a
kind and mapping, then `pull_source` — or `ingest_source` for a push. Auto-pull
sources run first in `tick`.

## Actions going out

Bind a target to an action type. When the action is *applied* (after approval),
Quinovo fires the target. A failed send is audited and **never undoes** the
local change. The ontology stays the system of record.

| Kind | What it does |
|------|----------------|
| Webhook / HTTP | POST the applied action to any URL. |
| Slack | Incoming webhook; a short human sentence. |
| Email | SMTP if you configure a host; otherwise the message is logged. |
| MCP | `tools/call` on a connected HTTP JSON-RPC endpoint. |
| Database write | Gated: `allow_write`, INSERT or UPDATE only, allow-listed tables, audited. |

## What this is not

It is not a marketplace. Salesforce, SAP, a warehouse, a custom app — they
all speak HTTP, SQL, a file, a push, or MCP. Point one of those adapters at
them. If a system already exposes MCP tools, that *is* the integration.
