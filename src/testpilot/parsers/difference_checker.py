from __future__ import annotations

from testpilot.domain.api import ApiDocument


def compare_documents(left: ApiDocument, right: ApiDocument) -> dict:
    left_map = {x.key: x for x in left.endpoints}
    right_map = {x.key: x for x in right.endpoints}
    shared = sorted(left_map.keys() & right_map.keys())
    differences = []
    for key in shared:
        a, b = left_map[key], right_map[key]
        a_params = {(x.name, x.location, x.required) for x in a.parameters}
        b_params = {(x.name, x.location, x.required) for x in b.parameters}
        if a_params != b_params or bool(a.security) != bool(b.security):
            differences.append({
                "endpoint": key,
                "left_only_parameters": sorted(a_params - b_params),
                "right_only_parameters": sorted(b_params - a_params),
                "security_mismatch": bool(a.security) != bool(b.security),
                "left_evidence": a.source_location,
                "right_evidence": b.source_location,
            })
    return {
        "left_only_endpoints": sorted(left_map.keys() - right_map.keys()),
        "right_only_endpoints": sorted(right_map.keys() - left_map.keys()),
        "shared_count": len(shared),
        "differences": differences,
    }

