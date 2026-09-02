# The ontology, told with a package

This file uses **one teaching pack** so every layer has a concrete sentence. Quinovo itself is domain-blind: you load whatever world you name. A clinic pack, a factory pack, a lab pack — same engine, different nouns.

Bob bought lipstick on Amazon. Amazon put it in a box. That is not four database tables. It is **one story**:

- a **Package** (the box, tracking `1Z999`)
- a **Product** (the lipstick)
- a **Person** (Bob, the buyer)
- a **Company** (Amazon, the shipper)

Those are **object types**. The arrows are **link types**:

- Package **contains** Product
- Package is **destined_for** Person
- Package is **shipped_by** Company

An ontology is that story, kept live, so a human *or an agent* can ask “what is Bob waiting on?” and do “mark this delivered” without writing SQL and without silently editing rows.

Anyone can swap the nouns. Factory: WorkOrder / Machine / Technician. Hospital: Bed / Patient / Ward. Homelab: Device / Service / Person. Same engine. The rest of this page stays with the box so the layers stay readable. It is still not the product.

## Where AI lives (the point)

Quinovo is not a chatbot with a database. Palantir’s AIP idea: the model only sees **objects** and only changes the world through **actions**. Hermes and Google ADK are the agent runtimes. Quinovo is the **world they are allowed to touch**.

Every layer either **feeds** an agent, **is proposed by** an agent, or **constrains** an agent.

---

### L1 — Dictionary (the types)

**Does:** Names the nouns and arrows. Package, Product, Person, Company, contains, destined_for, shipped_by.

**AI:** You do not have to hand-write YAML forever. An agent reads Shopify exports, invoices, or a PDF packing slip and *proposes* object types and links (“this column looks like a buyer”). A human (or a policy) accepts. Graphify-style extraction is this layer: structure from messy files. The compiled schema then becomes tools the agent can see.

**Automate:** `quinovo propose-ontology ./raw-exports` → diff → apply.

---

### L2 — Mailroom (data in, edits kept)

**Does:** Amazon’s nightly dump becomes Package objects. If an agent already marked `1Z999` delivered, tonight’s dump does not reopen it unless you say so.

**AI:** Connectors can be written by an agent (“poll this API, map tracking_id → Package.id”). The Funnel still owns merge rules. The agent does not get to invent overwrite policy.

**Automate:** register a connector, schedule sync, no human copy-paste.

---

### L3 — Card catalog (ask the story)

**Does:** `get Package 1Z999`. Walk **destined_for** → Bob. Walk **contains** → lipstick. “All packages shipped_by Amazon that are not delivered.”

**AI:** The agent never writes SQL. Hermes/ADK tools are generated: `get_object`, `search_around`, `filter`. “What’s in Bob’s box?” is `search_around(Package, 1Z999, contains)`.

**Automate:** every new object type immediately becomes a tool. Zero hand-wired endpoints.

---

### L4 — Graph paper (time and files)

**Does:** The package’s GPS / scan events are a **chart on the Package**, not a million tiny objects. A photo of the porch is a file on the Package.

**AI:** TimesFM (or any model) reads the scan series and writes `eta_p90` on the same Package. An agent can say “Bob’s lipstick is likely late” because that number lives on the object.

**Automate:** series ingest + forecast job on a timer.

---

### L5 — Official stamp (verbs)

**Does:** **mark_delivered** is how a Package becomes delivered. Not PATCH. Not “the LLM updated the JSON.” Same stamp for Bob’s app, a warehouse scanner, and an agent.

**AI:** The agent’s tool is `apply_action("mark_delivered", package=1Z999)`. If it is not allowed, it fails. The audit log says which agent did it. That is Palantir kinetics.

**Automate:** scanners and agents submit the same action type. No second write path.

---

### L6 — Calculator (logic / inference)

**Does:** New truth the dump never contained. Pack rules (then Python functions) walk **typed** objects, named links, and forecasts. Amazon said “in transit.” Inference says `at_risk` because `late_risk ≥ 0.25`, then `recommended_action=notify_buyer:Person:bob` because the `buyer` link exists. Observed properties stay observed. Inferred facts have a rule, a confidence, and provenance.

**AI:** This is not SPARQL over a blob of triples and not GraphRAG. Premises are Package / Person / `destined_for` / a forecast on that Package. Below 80% the conclusion is pending HITL. A later LLM function can propose rules; it still cannot invent Bob.

**Automate:** `POST /inference/run` after forecasts land; agents read asserted facts only.

---

### L7 — Locks

**Does:** Bob sees his packages. Warehouse sees in-flight. Amazon’s agent cannot mark a UPS package delivered.

**AI:** The agent inherits a user or a robot identity. Tools are already filtered. Prompt injection cannot “show me all buyers” if OpenFGA says no.

**Automate:** pack ships a default policy; you do not hand-roll ACLs per chatbot.

---

### L8 — Forecasts and what-ifs

**Does:** Predicted delay is a property on Package. A **scenario**: “what if we reroute via Memphis?” without touching production.

**AI:** Forecast models and LLM planners write onto objects or into a scenario overlay. They still commit through actions.

**Automate:** nightly forecast; weekly eval (were we actually late?).

---

### L9 — Plugs (Hermes, Google ADK, MCP, any SDK)

**Does:** The ontology *is* the agent backend. Generate:

- OpenAPI / typed SDK
- **MCP** tools (Cursor, Claude, Hermes plugins)
- **Google ADK** `FunctionTool`s from the same schema
- **Hermes** skill/plugin that only exposes get/searchAround/apply_action

You do not glue GPT to Postgres. You glue any agent kit to Quinovo.

**Automate:** schema change → regenerate tools → agents pick up new types (new “Warehouse” object appears as a tool the next process restart).

---

### L10 — Screens

**Does:** A page for Package `1Z999`: lipstick, Bob, Amazon, the tracking chart, the **Mark delivered** button (that button *is* the action).

**AI:** Same page can be driven by an agent (“summarize this object view”). Core view is generated from the type so you do not build a custom app per domain.

**Automate:** new object type → default Object View, no frontend ticket.

---

### L11 — Packs (anyone’s purpose)

**Does:** `packs/example` is ecommerce (Package/Product/Person/Company). `packs/homelab` is your lab (Device/Service). `packs/clinic` is someone else’s. The engine does not know Amazon or Jetson.

**AI:** An agent can author a pack from a description: “I run a dental office.” Propose types, you accept, Funnel + tools appear.

**Automate:** pack install is the product for GitHub users: `quinovo init --pack example` and they have an ontology + agent tools.

---

## One sentence per layer (keep this)

| Layer | In the package story | AI’s job |
|-------|----------------------|----------|
| L0 | Computers and clocks | — |
| L1 | Name Package, Bob, Amazon, the arrows | Propose the dictionary from messy data |
| L2 | Amazon dump → objects; do not wipe agent edits | Write/run connectors |
| L3 | “What did Bob buy?” via links | Only tool it gets for reading |
| L4 | Tracking chart on the box | Forecast late onto the same box |
| L5 | mark_delivered | Only tool it gets for changing the world |
| L6 | at_risk / notify Bob from typed rules | Deduce on objects+links+forecasts; HITL under 80% |
| L7 | Bob ≠ Alice | Agent identity ∩ object ACL |
| L8 | ETA on the package; what-if reroute | Models write properties; still commit via L5 |
| L9 | Hermes / ADK / MCP | Auto-generated tools from L1 |
| L10 | The package page | Generated UI + agent summary |
| L11 | This shop vs your lab vs a hospital | Agent can draft a new pack |

If the agent can `UPDATE packages SET status=...`, Quinovo has failed. If it can only `apply_action(mark_delivered)` and we logged it, Quinovo is doing the job.
