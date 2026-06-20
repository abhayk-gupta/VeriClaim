"""
Load per-store claim policies from YAML, keyed by `Order.policy_id`.

Policies live in the top-level `policies/` directory as `{policy_id}_policy.yaml`.
Loaded files are cached in-process. An unknown policy_id falls back to `default`.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# repo_root/policies — this file is app/langgraph_agent/tools/policy_loader.py
_POLICY_DIR = Path(__file__).resolve().parents[3] / "policies"


@lru_cache(maxsize=32)
def load_policy(policy_id: str) -> dict:
    path = _POLICY_DIR / f"{policy_id}_policy.yaml"
    if not path.exists():
        if policy_id != "default":
            logger.warning("Policy %r not found, falling back to default", policy_id)
            return load_policy("default")
        raise FileNotFoundError(f"Default policy missing at {path}")

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data
