# Framework for anyone, tested on the homelab

Quinovo is a **framework**. Anyone should be able to load their own world (factory, clinic, SaaS ops, another lab) without forking the engine. The **homelab is the first customer of that framework**, not the product.

This is Palantir’s split too: Foundry is domain-neutral; the airline/hospital/plant ontology is what the customer builds *in* it.

## Two boxes

| | Framework (`packages/`, `apps/`) | Homelab pack (`packs/homelab`) |
|--|----------------------------------|--------------------------------|
| Job | Language, funnel, object reads, actions, functions, security, SDK, MCP | The story: Device, Service, Alert, Tailscale connector, TimesFM on CPU |
| May know | Object, link, action, series, user | heater, xtal, Tailscale, Jetson, node_exporter |
| Must run | `make dev` on a laptop with fixture JSON, no Tailscale, no GPU | Against the real tailnet when you want proof |
| If it breaks | The kernel is wrong | The pack or the lab is wrong |

If `packages/engine` imports a Jetson thermal path or the string `"heater"`, the design has already failed.

## How you test without lying

1. **Framework tests** use a tiny built-in pack (`packs/example` or fixtures): three object types, two links, one action, JSON files instead of Tailscale. CI and `make dev` never need your house.
2. **Homelab tests** are integration: Funnel reads `tailscale status`, objects appear, `acknowledge_alert` is audited. That proves connectors and a real pack, not the kernel’s identity.
3. **The honesty check** is a *second* pack (orders/shipments, or even a fake warehouse) loaded with the same engine. Until that works, “framework for anyone” is a README claim.

Homelab is the **dogfood** path: messy identity (Tailscale node IDs vs hostnames), laptops that sleep, personal vs lab devices, time series, forecasts. If the framework can model that without special-casing NVIDIA, it can model a plant.

## What goes where (simple)

**Framework** owns: schema compiler, object store API, named links, actions + audit, locks, “a series is a property,” “a model writes onto an object,” generated SDK, MCP.

**Homelab pack** owns: object types (`Device`, `Service`, …), Tailscale/node_exporter connectors, `class=lab|personal|workstation`, where TimesFM runs (pi5, not the Orin), which alerts exist.

**Someone else** copies `packs/homelab` as a template, deletes Jetsons, writes `packs/acme-warehouse`. Same `make dev`. Same action-audit rule.

## What we will not do

- Ship Quinovo as “home lab surveillance.” That is one pack’s README.
- Require Tailscale, Jetson, or TimesFM to run the framework.
- Put Graphify or TimesFM inside the engine. They are optional pack/plugins (wiki indexer; one Model backend).
- Let xtal sleeping look like a framework outage. Presence rules live in the pack.

## Acceptance sentence

> A stranger can `make dev`, get a typed ontology with one audited action, and never hear the word heater. You can point the same binary at `packs/homelab` and see xtal and heater as objects.
