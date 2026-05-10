from __future__ import annotations

import json
import os

from tendersignal.config import TENDERSIGNAL_ENABLE_LLM, TENDERSIGNAL_LLM_MODEL, TENDERSIGNAL_LLM_PROVIDER


def maybe_polish_action_outputs(source_payload: dict[str, object], deterministic_outputs: dict[str, str]) -> dict[str, str]:
    """Optionally polish action outputs with a small LLM.

    The default path returns deterministic outputs at zero cost. If enabled, the
    LLM receives only source-grounded fields and must return JSON with the same
    keys. This is intended for tone/structure, not new facts.
    """

    if not (TENDERSIGNAL_ENABLE_LLM and TENDERSIGNAL_LLM_PROVIDER == "openai"):
        return deterministic_outputs
    if not os.environ.get("OPENAI_API_KEY"):
        return deterministic_outputs | {"LLM status": "Skipped: OPENAI_API_KEY missing."}

    try:
        from openai import OpenAI
    except ImportError:
        return deterministic_outputs | {"LLM status": "Skipped: optional openai package not installed."}

    client = OpenAI()
    response = client.responses.create(
        model=TENDERSIGNAL_LLM_MODEL,
        instructions=(
            "Polish procurement sales action outputs. Use only the supplied source_payload and deterministic_outputs. "
            "Do not add facts, values, requirements, customer history, names or dates not present in the input. "
            "Return compact JSON with keys: CRM task, Sales message, Qualification checklist."
        ),
        input=json.dumps(
            {"source_payload": source_payload, "deterministic_outputs": deterministic_outputs},
            ensure_ascii=False,
        ),
        text={"format": {"type": "json_object"}},
        temperature=0,
    )
    try:
        polished = json.loads(getattr(response, "output_text", ""))
    except json.JSONDecodeError:
        return deterministic_outputs | {"LLM status": "Skipped: non-JSON LLM response."}
    return {key: str(polished.get(key, deterministic_outputs.get(key, ""))) for key in deterministic_outputs}
