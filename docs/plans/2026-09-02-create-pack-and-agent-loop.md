# Create Pack + Autonomous Agent Loop

> **For Hermes:** Implement task-by-task in this single session, TDD, one commit per task.

**Goal:** Add (a) programmatic pack creation (`quinovo create` + MCP `create_pack`) and (b) a goal-driven autonomous agent loop the kernel can run without prompting, then wire them so the agent can use `create_pack` to grow the world.

**Architecture:** Two new modules — `quinovo/pack_create.py` (pure Python scaffold, validates by loading through `load_ontology`/`load_ruleset`) and `quinovo/agent.py` (policy-gated executor that calls existing kernel methods, never bypasses `apply_action`). Both exposed via Kernel methods, MCP tools, and CLI subcommands. The agent loop calls `create_pack` and `run_inference` to validate its own work.

**Tech Stack:** Python 3.12, Pydantic, PyYAML, existing `quinovo.kernel.Kernel` and `quinovo.cli`.

---

## Task 1: `quinovo pack_create` — scaffold a new pack from a spec

### Task 1.1: Failing test for `create_pack` from a dict spec

**Files:**
- Create: `tests/test_pack_create.py`

**Step 1: Write failing test**

```python
from pathlib import Path
from quinovo.pack_create import create_pack


def test_create_pack_writes_minimum_files(tmp_path: Path):
    spec = {
        "ontology": {
            "api_name": "tmpspec",
            "display_name": "Tmp Spec",
            "description": "test",
            "object_types": [
                {
                    "api_name": "Widget",
                    "primary_key": "id",
                    "title_property": "name",
                    "description": "a widget",
                    "properties": [
                        {"api_name": "id", "type": "string"},
                        {"api_name": "name", "type": "string"},
                    ],
                }
            ],
        },
        "seed": {
            "objects": {"Widget": [{"id": "w1", "name": "first"}]},
            "links": [],
        },
    }
    out = create_pack(tmp_path / "myworld", spec)
    assert (out / "ontology.yaml").exists()
    assert (out / "seed.yaml").exists()
    assert out.name == "myworld"
```

**Step 2: Verify RED**

```bash
cd /home/cfollette18/projects/Quinovo && uv run pytest tests/test_pack_create.py -v
```
Expected: ImportError or AttributeError.

**Step 3: Implement `quinovo/pack_create.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quinovo.language.load import load_ontology
from quinovo.inference.load import load_ruleset
from quinovo.funnel.seed import load_seed
from quinovo.engine.store import ObjectStore


class PackCreateError(ValueError):
    """Pack spec rejected."""


def create_pack(dest: Path, spec: dict[str, Any]) -> Path:
    dest = dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        raise PackCreateError(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)

    if "ontology" not in spec:
        raise PackCreateError("spec missing 'ontology'")
    ontology_yaml = yaml.safe_dump(spec["ontology"], sort_keys=False)
    (dest / "ontology.yaml").write_text(ontology_yaml, encoding="utf-8")

    if "inference" in spec:
        (dest / "inference.yaml").write_text(
            yaml.safe_dump(spec["inference"], sort_keys=False), encoding="utf-8"
        )

    if "seed" in spec:
        (dest / "seed.yaml").write_text(
            yaml.safe_dump(spec["seed"], sort_keys=False), encoding="utf-8"
        )

    # Validate by loading through the real loaders — fails fast on bad spec.
    load_ontology(dest / "ontology.yaml")
    if "inference" in spec:
        load_ruleset(dest / "inference.yaml")
    return dest


def create_and_seed(dest: Path, spec: dict[str, Any], db_path: Path) -> tuple[Path, ObjectStore]:
    pack_dir = create_pack(dest, spec)
    ontology = load_ontology(pack_dir / "ontology.yaml")
    store = ObjectStore(ontology, db_path)
    if "seed" in spec:
        # load_seed needs the ontology-attached store; pass it directly
        from quinovo.funnel.seed import load_seed as _load_seed
        _load_seed(store, pack_dir / "seed.yaml")
    return pack_dir, store
```

**Step 4: Verify GREEN**

```bash
uv run pytest tests/test_pack_create.py::test_create_pack_writes_minimum_files -v
```

**Step 5: Commit**

```bash
git add tests/test_pack_create.py src/quinovo/pack_create.py
git commit -m "feat(pack): quinovo.pack_create creates a new pack from a spec dict"
```

### Task 1.2: Failing test — validation rejects bad ontology

```python
def test_create_pack_rejects_invalid_ontology(tmp_path: Path):
    from quinovo.pack_create import create_pack, PackCreateError
    bad = {"ontology": {"api_name": "x"}}  # no object_types
    try:
        create_pack(tmp_path / "bad", bad)
    except PackCreateError:
        return
    raise AssertionError("expected PackCreateError")
```

Run test — verify FAIL — fix nothing (the implementation already raises via load_ontology). Run test — verify PASS. Commit.

### Task 1.3: CLI subcommand `quinovo create`

**Files:**
- Modify: `src/quinovo/cli.py`

Add subparser `create` accepting `--from-spec PATH` and `dest`. Read YAML, call `create_pack`, print path. Add test in `tests/test_pack_create.py` that runs `python -m quinovo.cli create <tmp> --from-spec <yaml>` via subprocess. Verify RED then GREEN. Commit.

### Task 1.4: Expose `create_pack` as a Kernel method and MCP tool

**Files:**
- Modify: `src/quinovo/kernel.py` — add `Kernel.create_pack(dest: Path, spec: dict) -> dict`
- Modify: `src/quinovo/mcp/server.py` — wire tool
- Modify: `src/quinovo/adapters.py` — add to `tool_specs()`

Add test that calls `kernel.create_pack(...)` and confirms MCP tool manifest includes `create_pack`. Verify GREEN. Commit.

---

## Task 2: Autonomous agent loop

### Task 2.1: Failing test for `Agent.run(goal)`

**Files:**
- Create: `src/quinovo/agent.py`
- Create: `tests/test_agent.py`

**Step 1: Test**

```python
from quinovo.agent import Agent, AgentStep


def test_agent_runs_steps_until_goal_met(tmp_path):
    from quinovo.kernel import open_kernel
    kernel = open_kernel(Path("packs/example"), tmp_path / "q.sqlite")
    agent = Agent(kernel, actor="test-agent")
    steps = agent.run("mark every Package delivered", max_steps=10)
    # Should observe + apply mark_delivered at least once
    actions = [s for s in steps if s.kind == "apply_action"]
    assert any(s.name == "mark_delivered" for s in actions)
    assert all(s.ok for s in steps)
```

**Step 2: Verify RED.**

**Step 3: Implement `quinovo/agent.py`**

Minimal policy-gated loop. Steps are: `list_objects` → `get_object` → `apply_action`. The agent NEVER writes directly — only via kernel methods, which already gate policy + HITL.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from quinovo.kernel import Kernel


@dataclass
class AgentStep:
    kind: Literal["list", "read", "apply_action", "inference"]
    name: str
    ok: bool
    detail: dict[str, Any]


class Agent:
    """
    Goal-driven executor over a Quinovo Kernel.

    The agent calls only kernel methods — it never writes to the store
    directly. apply_action calls go through the kernel's policy gates
    (HITL, unattended flag, asserted_recommendation).

    Goals are matched against action verbs in the loaded ontology:
    "mark X delivered" → list_packages → for each, apply_action('mark_delivered', ...).
    """

    def __init__(self, kernel: Kernel, actor: str = "quinovo-agent") -> None:
        self.kernel = kernel
        self.actor = actor

    def run(self, goal: str, max_steps: int = 20) -> list[AgentStep]:
        steps: list[AgentStep] = []
        verbs = self._verbs_from_goal(goal)
        actions = self.kernel.list_actions().get("actions", [])
        action_names = {a["api_name"] for a in actions}
        for verb in verbs:
            if verb not in action_names:
                steps.append(AgentStep("list", verb, False, {"reason": "unknown verb"}))
                continue
            # Find which type this action targets
            action_def = next(a for a in actions if a["api_name"] == verb)
            target_type = action_def["parameters"][0]["object_type"]
            listed = self.kernel.filter_objects(target_type)
            steps.append(AgentStep("list", target_type, True, {"count": len(listed["objects"])}))
            for obj in listed["objects"]:
                try:
                    result = self.kernel.apply_action(
                        verb,
                        {action_def["parameters"][0]["api_name"]: {"id": obj["id"]}},
                        actor=self.actor,
                        channel="mcp",
                    )
                    steps.append(AgentStep("apply_action", verb, True, {"id": obj["id"], **result}))
                except Exception as exc:
                    steps.append(AgentStep("apply_action", verb, False, {"id": obj["id"], "error": str(exc)}))
            if len(steps) >= max_steps:
                break
        return steps

    @staticmethod
    def _verbs_from_goal(goal: str) -> list[str]:
        actions_path = Path(__file__).resolve().parent.parent.parent / "packs" / "example" / "ontology.yaml"
        # Discoverable verbs: any word that exactly matches an action api_name.
        words = {w.strip(".,;:!?") for w in goal.split()}
        return [w for w in words if "_" in w or w in {"delivered", "acked"}]
```

**Step 4: Verify GREEN.** If the heuristic misses, extend `_verbs_from_goal` to read the kernel's action list. Iterate until `mark_delivered` fires.

**Step 5: Commit**

```bash
git add tests/test_agent.py src/quinovo/agent.py
git commit -m "feat(agent): goal-driven Agent executor with policy gates"
```

### Task 2.2: Failing test — agent can call `create_pack` to grow the world

```python
def test_agent_can_create_pack_via_goal(tmp_path):
    from quinovo.kernel import open_kernel
    from quinovo.agent import Agent
    kernel = open_kernel(Path("packs/example"), tmp_path / "q.sqlite")
    agent = Agent(kernel, actor="agent-create")
    # Seed an empty ontology plus a goal that asks to add a type.
    spec = {
        "ontology": {
            "api_name": "grown",
            "display_name": "Grown",
            "description": "agent-grown",
            "object_types": [
                {
                    "api_name": "Node",
                    "primary_key": "id",
                    "title_property": "id",
                    "description": "n",
                    "properties": [{"api_name": "id", "type": "string"}],
                }
            ],
        }
    }
    out = kernel.create_pack(tmp_path / "grown", spec)
    assert (out / "ontology.yaml").exists()
    # Agent run with a 'create_pack' verb in the goal should call create_pack
    steps = agent.run("create_pack grown", max_steps=3)
    assert any(s.kind == "create_pack" for s in steps)
```

Extend `Agent._verbs_from_goal` and `Agent.run` to recognize `create_pack` and dispatch through the kernel. Iterate. Commit.

### Task 2.3: Expose `Agent.run` as `Kernel.run_agent` and as MCP tool `run_agent`

**Files:**
- Modify: `src/quinovo/kernel.py` — `Kernel.run_agent(goal, max_steps)` returns `{steps: [...]}`
- Modify: `src/quinovo/mcp/server.py` — add tool wrapper
- Modify: `src/quinovo/adapters.py` — add to `tool_specs()`

Add test in `tests/test_agent.py` that hits `kernel.run_agent(...)` and verifies return shape. Commit.

### Task 2.4: CLI subcommand `quinovo agent <goal>`

**Files:**
- Modify: `src/quinovo/cli.py`

Subparser `agent` accepting `--pack`, `--db`, `--goal`, `--max-steps`. Print each step as one line. Add subprocess test. Commit.

---

## Task 3: Integration test — agent grows the world and uses it

```python
def test_agent_creates_pack_then_acts_in_it(tmp_path):
    from quinovo.kernel import open_kernel
    from quinovo.agent import Agent
    kernel = open_kernel(Path("packs/example"), tmp_path / "q.sqlite")
    agent = Agent(kernel, actor="agent-grow")
    spec = {
        "ontology": {
            "api_name": "lab",
            "display_name": "Lab",
            "description": "grown",
            "object_types": [
                {
                    "api_name": "Sample",
                    "primary_key": "id",
                    "title_property": "id",
                    "description": "s",
                    "implements": ["Trackable"],
                    "properties": [
                        {"api_name": "id", "type": "string"},
                        {"api_name": "status", "type": "string"},
                    ],
                }
            ],
            "action_types": [
                {
                    "api_name": "process_sample",
                    "description": "p",
                    "parameters": [{"api_name": "sample", "type": "object", "object_type": "Sample"}],
                    "edits": [{"parameter": "sample", "set": {"status": "processed"}}],
                }
            ],
        },
        "seed": {"objects": {"Sample": [{"id": "s1", "status": "raw"}]}, "links": []},
    }
    out = kernel.create_pack(tmp_path / "lab", spec)
    # Open the new pack and run the agent there
    new_kernel = open_kernel(out, tmp_path / "lab.sqlite")
    new_agent = Agent(new_kernel, actor="lab-agent")
    steps = new_agent.run("process_sample", max_steps=5)
    assert any(s.kind == "apply_action" and s.name == "process_sample" and s.ok for s in steps)
```

Verify GREEN. Commit.

---

## Task 4: Docs + README update

Update `README.md` to mention `quinovo create`, `quinovo agent`, and the new MCP tools. Run full suite one last time. Final commit.
