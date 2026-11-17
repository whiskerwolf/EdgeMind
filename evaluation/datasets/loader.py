"""
Dataset Loader & Validation Utilities.

Loads, validates, and queries evaluation datasets using Pydantic schemas.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
from pydantic import ValidationError

from evaluation.schemas.dataset import EvaluationDataset


DEFAULT_DATASET_PATH = Path(__file__).parent / "coding_problems.json"


def load_dataset_from_file(path: Union[str, Path]) -> EvaluationDataset:
    """
    Load and strictly validate an evaluation dataset from a JSON file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If JSON is invalid or fails Pydantic schema validation.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Evaluation dataset file not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in evaluation dataset '{file_path}': {exc}") from exc

    return validate_dataset_dict(data)


def validate_dataset_dict(data: Dict[str, Any]) -> EvaluationDataset:
    """
    Validate a raw dictionary against the EvaluationDataset Pydantic model.

    Raises:
        ValueError: With formatted validation error details if invalid.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Dataset root must be a JSON object, got {type(data).__name__}.")

    try:
        return EvaluationDataset(**data)
    except ValidationError as exc:
        errors = exc.errors()
        error_details = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
            for err in errors
        )
        raise ValueError(f"Evaluation dataset schema validation failed: {error_details}") from exc


def load_default_dataset() -> EvaluationDataset:
    """Load the default representative 22-problem coding benchmark."""
    return load_dataset_from_file(DEFAULT_DATASET_PATH)
