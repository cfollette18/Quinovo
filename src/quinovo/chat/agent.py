"""Streaming agent loop for workspace chat. Tools are the Quinovo MCP surface."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from quinovo.chat.sessions import (
    get_session,
    new_session,
    save_session,
    title_from_text,
)
from quinovo.chat.tools import (
    anthropic_tools,
    dispatch_tool,
    openai_tools,
    tool_event,
)
from quinovo.kernel import Kernel
from quinovo.llm.engine import LLMError
from quinovo.llm.settings import LLMSettings, ensure_settings
from quinovo.llm.tracing import observe_generation, trace_operation

MAX_ROUNDS = 16
MAX_TOKENS = 4096


def system_prompt(kernel: Kernel) -> str:
    pack = kernel.ontology.ontology.display_name
    threshold = kernel.ontology.ontology.auto_apply_min_confidence
    types = ", ".join(item.api_name for item in kernel.ontology.object_types[:24])
    return (
        "You are Quinovo Chat, a coding-agent over an operational ontology. "
        f"Workspace: {pack}. Kinds in this pack include: {types}. "
        "You have the full Quinovo MCP tool surface. Prefer tools over memory. "
        "When the user names something, call find_objects first, then get_object "
        "or search_around. Use filter_objects, list_inferred_facts, graph, tick, "
        "and the other MCP tools when they fit. Never invent objects, links, "
        "facts, or ids the tools did not return. Speak in plain language — short "
        "sentences, no JSON, no YAML, no SQL, no code fences of structured data. "
        "Name things the way a person would (Audit criterion, not AuditCriterion). "
        f"Do not approve or reject HITL items unless the user named that item. "
        f"Below {threshold} confidence, proposals park for a look; at or above, they apply. "
        "Do not call remember or save_turn unless the user asked to store something extra. "
        "Call tick only when they want a fresh pass now. "
        "If nothing matches, say so and suggest a next question."
    )


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def _iter_sse(response: httpx.Response) -> Iterator[dict[str, Any]]:
    data_lines: list[str] = []
    for line in response.iter_lines():
        if line is None:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
        if line != "":
            continue
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        data_lines = []
        if raw.strip() in {"[DONE]", ""}:
            if raw.strip() == "[DONE]":
                return
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload
    if data_lines:
        raw = "\n".join(data_lines)
        if raw.strip() and raw.strip() != "[DONE]":
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return
            if isinstance(payload, dict):
                yield payload


def _anthropic_headers(settings: LLMSettings, *, stream: bool = False) -> dict[str, str]:
    headers = {
        "x-api-key": settings.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    if stream:
        headers["accept"] = "text/event-stream"
    return headers


def _openai_headers(settings: LLMSettings, *, stream: bool = False) -> dict[str, str]:
    headers = {
        "authorization": f"Bearer {settings.api_key}",
        "content-type": "application/json",
    }
    if stream:
        headers["accept"] = "text/event-stream"
    return headers


def _anthropic_body(settings: LLMSettings, messages: list[dict[str, Any]], system: str) -> dict[str, Any]:
    return {
        "model": settings.model,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": messages,
        "tools": anthropic_tools(),
    }


def _openai_body(settings: LLMSettings, messages: list[dict[str, Any]], system: str) -> dict[str, Any]:
    return {
        "model": settings.model,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "system", "content": system}, *messages],
        "tools": openai_tools(),
    }


def _anthropic_nonstream(
    settings: LLMSettings, messages: list[dict[str, Any]], system: str
) -> tuple[str, list[dict[str, Any]], str]:
    url = f"{settings.base_url.rstrip('/')}/v1/messages"
    response = httpx.post(
        url,
        headers=_anthropic_headers(settings),
        json=_anthropic_body(settings, messages, system),
        timeout=90.0,
    )
    if response.status_code >= 400:
        raise LLMError(f"{response.status_code}: {response.text[:400]}")
    data = response.json()
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in data.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") in (None, "text"):
            text_parts.append(str(block.get("text") or ""))
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "arguments": _parse_arguments(block.get("input")),
                }
            )
    stop = str(data.get("stop_reason") or ("tool_use" if tool_calls else "end_turn"))
    return "".join(text_parts), tool_calls, stop


def _openai_nonstream(
    settings: LLMSettings, messages: list[dict[str, Any]], system: str
) -> tuple[str, list[dict[str, Any]], str]:
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    response = httpx.post(
        url,
        headers=_openai_headers(settings),
        json=_openai_body(settings, messages, system),
        timeout=90.0,
    )
    if response.status_code >= 400:
        raise LLMError(f"{response.status_code}: {response.text[:400]}")
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return "", [], "stop"
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "")
    tool_calls: list[dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        tool_calls.append(
            {
                "id": str(call.get("id") or ""),
                "name": str(fn.get("name") or ""),
                "arguments": _parse_arguments(fn.get("arguments")),
            }
        )
    finish = str(choices[0].get("finish_reason") or "stop")
    stop = "tool_use" if finish == "tool_calls" or tool_calls else "end_turn"
    return text, tool_calls, stop


def _anthropic_stream(
    settings: LLMSettings, messages: list[dict[str, Any]], system: str
) -> Iterator[dict[str, Any]]:
    url = f"{settings.base_url.rstrip('/')}/v1/messages"
    body = {**_anthropic_body(settings, messages, system), "stream": True}
    text_parts: list[str] = []
    tools: dict[int, dict[str, Any]] = {}
    stop = "end_turn"
    with httpx.Client(timeout=90.0) as client, client.stream(
        "POST", url, headers=_anthropic_headers(settings, stream=True), json=body
    ) as response:
        if response.status_code >= 400:
            raw = response.read().decode("utf-8", errors="replace")[:400]
            raise LLMError(f"{response.status_code}: {raw}")
        for event in _iter_sse(response):
            kind = str(event.get("type") or "")
            if kind == "content_block_start":
                block = event.get("content_block") or {}
                index = int(event.get("index") or 0)
                if block.get("type") == "tool_use":
                    tools[index] = {
                        "id": str(block.get("id") or ""),
                        "name": str(block.get("name") or ""),
                        "json": "",
                    }
            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta":
                    chunk = str(delta.get("text") or "")
                    if chunk:
                        text_parts.append(chunk)
                        yield {"type": "text", "text": chunk}
                elif delta.get("type") == "input_json_delta":
                    index = int(event.get("index") or 0)
                    if index in tools:
                        tools[index]["json"] += str(delta.get("partial_json") or "")
            elif kind == "message_delta":
                stop = str((event.get("delta") or {}).get("stop_reason") or stop)
    calls = [
        {
            "id": item["id"],
            "name": item["name"],
            "arguments": _parse_arguments(item.get("json") or "{}"),
        }
        for _, item in sorted(tools.items())
    ]
    if calls and stop == "end_turn":
        stop = "tool_use"
    yield {"type": "turn", "text": "".join(text_parts), "calls": calls, "stop": stop}


def _openai_stream(
    settings: LLMSettings, messages: list[dict[str, Any]], system: str
) -> Iterator[dict[str, Any]]:
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    body = {**_openai_body(settings, messages, system), "stream": True}
    text_parts: list[str] = []
    tools: dict[int, dict[str, Any]] = {}
    stop = "end_turn"
    with httpx.Client(timeout=90.0) as client, client.stream(
        "POST", url, headers=_openai_headers(settings, stream=True), json=body
    ) as response:
        if response.status_code >= 400:
            raw = response.read().decode("utf-8", errors="replace")[:400]
            raise LLMError(f"{response.status_code}: {raw}")
        for event in _iter_sse(response):
            choices = event.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            chunk = delta.get("content")
            if chunk:
                piece = str(chunk)
                text_parts.append(piece)
                yield {"type": "text", "text": piece}
            for call in delta.get("tool_calls") or []:
                index = int(call.get("index") or 0)
                slot = tools.setdefault(index, {"id": "", "name": "", "json": ""})
                if call.get("id"):
                    slot["id"] = str(call["id"])
                fn = call.get("function") or {}
                if fn.get("name"):
                    slot["name"] = str(fn["name"])
                if fn.get("arguments"):
                    slot["json"] += str(fn["arguments"])
            finish = choice.get("finish_reason")
            if finish == "tool_calls":
                stop = "tool_use"
            elif finish:
                stop = "end_turn"
    calls = [
        {
            "id": item["id"],
            "name": item["name"],
            "arguments": _parse_arguments(item.get("json") or "{}"),
        }
        for _, item in sorted(tools.items())
        if item.get("name")
    ]
    if calls and stop == "end_turn":
        stop = "tool_use"
    yield {"type": "turn", "text": "".join(text_parts), "calls": calls, "stop": stop}


def complete_turn(
    settings: LLMSettings,
    messages: list[dict[str, Any]],
    system: str,
) -> Iterator[dict[str, Any]]:
    """Yield text deltas, then a final turn event with full text and tool calls."""
    streamed = False

    def fallback() -> tuple[str, list[dict[str, Any]], str]:
        captured: dict[str, Any] = {}

        def wrapped() -> tuple[str, dict[str, int], dict[str, Any]]:
            match settings.protocol:
                case "anthropic":
                    text, calls, stop = _anthropic_nonstream(settings, messages, system)
                case "openai":
                    text, calls, stop = _openai_nonstream(settings, messages, system)
                case _ as unreachable:
                    raise LLMError(f"unhandled protocol {unreachable!r}")
            captured["calls"] = calls
            captured["stop"] = stop
            return text, {}, {"tool_calls": calls, "stop": stop}

        text = observe_generation(
            name="workspace-chat",
            model=settings.model,
            protocol=settings.protocol,
            provider=settings.provider,
            prompt=json.dumps(messages[-1], default=str)[:800],
            run=wrapped,
        )
        return text, list(captured.get("calls") or []), str(captured.get("stop") or "end_turn")

    try:
        match settings.protocol:
            case "anthropic":
                stream = _anthropic_stream(settings, messages, system)
            case "openai":
                stream = _openai_stream(settings, messages, system)
            case _ as unreachable:
                raise LLMError(f"unhandled protocol {unreachable!r}")
        for event in stream:
            streamed = True
            yield event
        return
    except LLMError:
        if streamed:
            raise
    except Exception:
        if streamed:
            raise

    text, calls, stop = fallback()
    if text:
        yield {"type": "text", "text": text}
    yield {"type": "turn", "text": text, "calls": calls, "stop": stop}


def complete_turn_raw(
    settings: LLMSettings,
    messages: list[dict[str, Any]],
    system: str,
) -> tuple[str, list[dict[str, Any]], str]:
    text = ""
    calls: list[dict[str, Any]] = []
    stop = "end_turn"
    for event in complete_turn(settings, messages, system):
        if event.get("type") == "turn":
            text = str(event.get("text") or text)
            calls = list(event.get("calls") or [])
            stop = str(event.get("stop") or stop)
        elif event.get("type") == "text" and not text:
            text += str(event.get("text") or "")
    return text, calls, stop


def _assistant_message_anthropic(text: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    for call in calls:
        content.append(
            {
                "type": "tool_use",
                "id": call["id"],
                "name": call["name"],
                "input": call.get("arguments") or {},
            }
        )
    return {"role": "assistant", "content": content or [{"type": "text", "text": ""}]}


def _tool_result_anthropic(call_id: str, payload: str) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": call_id, "content": payload}


def _execute_tool(kernel: Kernel, call: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    name = str(call.get("name") or "")
    args = call.get("arguments") or {}
    tool_id = str(call.get("id") or name)
    payload, summary = dispatch_tool(kernel, name, args)
    row = tool_event(name, args, tool_id=tool_id, status="done", summary=summary)
    return tool_id, payload, row


def _yield_tools(
    kernel: Kernel,
    calls: list[dict[str, Any]],
    tool_trace: list[dict[str, Any]],
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for call in calls:
        name = str(call.get("name") or "")
        args = call.get("arguments") or {}
        tool_id = str(call.get("id") or name)
        yield ("event", "", tool_event(name, args, tool_id=tool_id, status="running"))
        tool_id, payload, row = _execute_tool(kernel, call)
        tool_trace.append(row)
        yield ("done", payload, row)


def run_agent(
    kernel: Kernel,
    history: list[dict[str, Any]],
    user_text: str,
    settings: LLMSettings | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield SSE-ready events: text, tool, error, then the caller persists."""
    cfg = settings or ensure_settings()
    if not cfg.ready():
        yield {
            "type": "error",
            "message": "Set the language model in Settings before chatting.",
        }
        return

    system = system_prompt(kernel)
    protocol = cfg.protocol
    messages: list[dict[str, Any]] = list(history)
    messages.append({"role": "user", "content": user_text})

    assistant_text = ""
    tool_trace: list[dict[str, Any]] = []

    with trace_operation("workspace-chat", trace_input={"text": user_text}, tags=["chat"]):
        for _round in range(MAX_ROUNDS):
            round_text = ""
            calls: list[dict[str, Any]] = []
            try:
                for event in complete_turn(cfg, messages, system):
                    if event.get("type") == "text":
                        chunk = str(event.get("text") or "")
                        if not chunk:
                            continue
                        if not round_text and assistant_text and not assistant_text[-1:].isspace():
                            assistant_text += "\n\n"
                            yield {"type": "text", "text": "\n\n"}
                        round_text += chunk
                        assistant_text += chunk
                        yield {"type": "text", "text": chunk}
                    elif event.get("type") == "turn":
                        full = str(event.get("text") or "")
                        leftover = full[len(round_text) :] if full.startswith(round_text) else ""
                        if leftover:
                            if not round_text and assistant_text and not assistant_text[-1:].isspace():
                                assistant_text += "\n\n"
                                yield {"type": "text", "text": "\n\n"}
                            round_text += leftover
                            assistant_text += leftover
                            yield {"type": "text", "text": leftover}
                        calls = list(event.get("calls") or [])
            except LLMError as exc:
                yield {"type": "error", "message": str(exc)[:400]}
                return
            except Exception as exc:
                yield {"type": "error", "message": str(exc)[:400]}
                return

            if not calls:
                break

            if protocol == "anthropic":
                messages.append(_assistant_message_anthropic(round_text, calls))
                results: list[dict[str, Any]] = []
                for kind, payload, row in _yield_tools(kernel, calls, tool_trace):
                    yield row
                    if kind == "done":
                        results.append(_tool_result_anthropic(str(row["id"]), payload))
                messages.append({"role": "user", "content": results})
            else:
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": round_text or None}
                openai_calls = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("arguments") or {}),
                        },
                    }
                    for call in calls
                ]
                if openai_calls:
                    assistant_msg["tool_calls"] = openai_calls
                messages.append(assistant_msg)
                for kind, payload, row in _yield_tools(kernel, calls, tool_trace):
                    yield row
                    if kind == "done":
                        messages.append(
                            {"role": "tool", "tool_call_id": str(row["id"]), "content": payload}
                        )
        else:
            yield {
                "type": "text",
                "text": " I stopped after too many steps. Ask a narrower question.",
            }

    yield {
        "type": "done",
        "text": assistant_text,
        "tools": tool_trace,
    }


def history_from_session(session_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prior turns as provider messages (user/assistant text only)."""
    out: list[dict[str, Any]] = []
    for item in session_messages:
        role = item.get("role")
        text = str(item.get("text") or "").strip()
        if role in {"user", "assistant"} and text:
            out.append({"role": role, "content": text})
    return out


def run_chat_turn(
    kernel: Kernel,
    user_text: str,
    *,
    history: list[dict[str, Any]] | None = None,
    settings: LLMSettings | None = None,
) -> Iterator[dict[str, Any]]:
    yield from run_agent(kernel, history or [], user_text, settings=settings)


def handle_user_message(
    kernel: Kernel,
    text: str,
    *,
    session_id: str = "",
    settings: LLMSettings | None = None,
) -> Iterator[dict[str, Any]]:
    cleaned = text.strip()
    if not cleaned:
        yield {"type": "error", "message": "Type a question first."}
        return
    if session_id:
        try:
            session = get_session(session_id)
        except KeyError:
            session = new_session(title_from_text(cleaned))
    else:
        session = new_session(title_from_text(cleaned))
    yield {"type": "session", "id": session.id, "title": session.title}
    prior = history_from_session(session.messages)
    session.messages.append({"role": "user", "text": cleaned, "tools": []})
    collected = ""
    tools: list[dict[str, Any]] = []
    for event in run_chat_turn(kernel, cleaned, history=prior, settings=settings):
        yield event
        if event.get("type") == "text":
            collected += str(event.get("text") or "")
        elif event.get("type") == "done":
            collected = str(event.get("text") or collected)
            tools = list(event.get("tools") or [])
        elif event.get("type") == "error" and not collected:
            collected = str(event.get("message") or "")
    session.messages.append({"role": "assistant", "text": collected, "tools": tools})
    save_session(session)
    try:
        kernel.remember(
            f"User asked: {cleaned}\nQuinovo answered: {collected}",
            topic="quinovo",
            session_id=session.id,
            role="workspace-chat",
            actor="workspace-chat",
        )
    except Exception:
        return
