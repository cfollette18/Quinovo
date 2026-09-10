"""Digital twin workspace. Phase 9 fills the live canvas; this is the rail home."""

from __future__ import annotations

from quinovo.apps.chrome import empty_state, page_head, wrap


def twin_html(pack_name: str = "") -> str:
    body = f"""
{page_head(
    "Twin",
    "Twin",
    "Live objects, named links, inferred facts, and forecasts — the digital twin.",
    "twin",
)}
<div class="page">
  {empty_state(
      "The twin is the live view",
      "Observed state, predicted state, and scenario overlays will land here. The graph canvas is ready now.",
      "/graph",
      "Open the graph",
  )}
</div>
"""
    return wrap("Twin", body, nav="twin", pack_name=pack_name)
