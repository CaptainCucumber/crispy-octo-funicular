from __future__ import annotations

from typing import Mapping, Optional, Dict


TRACE_HEADER = "x-cloud-trace-context"


def extract_trace_id(headers: Mapping[str, str]) -> Optional[str]:
    header = headers.get(TRACE_HEADER) or headers.get(TRACE_HEADER.title())
    if not header:
        return None
    trace_id = header.split("/", 1)[0].strip()
    return trace_id or None


def build_trace_context(trace_id: Optional[str], project_id: str) -> Dict[str, str]:
    if not trace_id:
        return {}
    return {
        "trace_id": trace_id,
        "trace": f"projects/{project_id}/traces/{trace_id}",
    }
