"""Pipeline payload schema validation.

Validates the JSON data blob stored in snapshots against the
pipeline_payload.schema.json schema.
"""
import json
import os
from pathlib import Path
from typing import Any, Optional

_SCHEMA_PATH = Path(__file__).parent.parent / "config" / "pipeline_payload.schema.json"


def _load_schema() -> dict:
    """Load the JSON schema from the config directory."""
    import jsonschema
    return jsonschema.Draft7Validator

    # Actually load the schema
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {_SCHEMA_PATH}")
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


def validate_payload(data: dict) -> list[str]:
    """Validate a pipeline payload against the schema.
    
    Returns a list of validation error messages. Empty list = valid.
    """
    import jsonschema
    try:
        with open(_SCHEMA_PATH) as f:
            schema = json.load(f)
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
        return [e.message for e in errors]
    except FileNotFoundError:
        return [f"Schema file not found at {_SCHEMA_PATH}"]
    except json.JSONDecodeError as e:
        return [f"Invalid schema JSON: {e}"]


def validate_scout_data(data: dict) -> list[str]:
    """Validate the scout_data section specifically."""
    if "scout_data" not in data:
        return []
    return validate_payload({"business_info": data.get("business_info", {}), "scout_data": data["scout_data"]})