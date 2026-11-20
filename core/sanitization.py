"""
EdgeMind Input Sanitization & Security Boundary Utilities.

Provides robust, layered sanitization for:
1. Source code validation (preserving syntax, quotes, brackets, operators, and code fences).
2. Null byte and unsafe control character stripping and rejection.
3. Unicode normalization (NFC) and safe surrogate handling.
4. Identifier, slug, and filename boundary validation (path traversal defense).
5. Problem context and tool argument data bounding.
6. Secret redaction (API keys, JWT tokens, database credentials).
7. XML structural tag boundary escaping to prevent prompt injection breakouts.
"""

from datetime import datetime
import json
import re
from typing import Any, Dict, List, Optional, Union
import unicodedata
import uuid

# Maximum byte limits
MAX_SOURCE_CODE_BYTES = 64 * 1024       # 64 KiB
MAX_PROBLEM_DESCRIPTION_CHARS = 32768   # 32 KiB
MAX_TITLE_CHARS = 255
MAX_SLUG_CHARS = 255
MAX_FILENAME_CHARS = 255
MAX_CONSTRAINTS_COUNT = 50
MAX_CONSTRAINT_ITEM_CHARS = 500
MAX_TEST_CASES_COUNT = 100
MAX_QUERY_CHARS = 2000
MAX_TOOL_NAME_CHARS = 64

# Tool argument recursive limits
MAX_TOOL_ARG_NESTING_DEPTH = 10
MAX_TOOL_ARG_DICT_ENTRIES = 1000
MAX_TOOL_ARG_LIST_LENGTH = 10000
MAX_TOOL_ARG_STRING_LENGTH = 65536      # 64 KiB, matching MAX_SOURCE_CODE_BYTES
MAX_TOOL_ARG_TOTAL_SERIALIZED_BYTES = 256 * 1024  # 256 KiB

# Regex patterns
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
SAFE_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{1,64}$")
SAFE_SLUG_PATTERN = re.compile(r"^[a-z0-9_-]{1,255}$")

# Common secret detection patterns for redaction
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]+", re.IGNORECASE),
    re.compile(r"(?:sk-(?:proj-)?[a-zA-Z0-9_\-]{20,}|AIza[0-9A-Za-z\-_]{30,})"),
    re.compile(r"((?:api[_-]?key|secret[_-]?key|password|jwt[_-]?secret)\s*[:=]\s*[\"']?)([^\s,;\"']+)([\"']?)", re.IGNORECASE),
]


def normalize_unicode(text: str) -> str:
    """
    Normalize text to Unicode NFC form and replace invalid surrogate code points
    to prevent UnicodeEncodeError in serialization or storage.
    """
    if not isinstance(text, str):
        return str(text)
    # Encode with surrogatepass and decode with replace to safely eliminate broken surrogates
    safe_text = text.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
    return unicodedata.normalize("NFC", safe_text)


def has_null_bytes(text: str) -> bool:
    """Check if a string contains null bytes."""
    return "\x00" in text or "\0" in text


def strip_null_bytes(text: str) -> str:
    """Remove null bytes from text."""
    if not text:
        return ""
    return text.replace("\x00", "").replace("\0", "")


def strip_unsafe_control_characters(
    text: str,
    keep_newlines: bool = True,
    keep_tabs: bool = True,
) -> str:
    """
    Strip ASCII control characters (0-31, 127) while optionally preserving
    standard whitespace formatting (newlines and tabs).
    """
    if not text:
        return ""

    allowed_controls = set()
    if keep_newlines:
        allowed_controls.update({"\n", "\r"})
    if keep_tabs:
        allowed_controls.add("\t")

    cleaned_chars = []
    for ch in text:
        code = ord(ch)
        if (code < 32 or code == 127) and ch not in allowed_controls:
            continue
        cleaned_chars.append(ch)

    return "".join(cleaned_chars)


def sanitize_text(
    text: str,
    max_length: int = 10000,
    allow_newlines: bool = True,
) -> str:
    """
    Standard text sanitizer:
    - Normalizes Unicode.
    - Strips null bytes.
    - Strips unsafe control characters.
    - Enforces maximum character length.
    """
    if not isinstance(text, str):
        text = str(text) if text is not None else ""

    normalized = normalize_unicode(text)
    stripped = strip_null_bytes(normalized)
    cleaned = strip_unsafe_control_characters(stripped, keep_newlines=allow_newlines)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned.strip()


def validate_source_code(
    code: str,
    max_bytes: int = MAX_SOURCE_CODE_BYTES,
) -> str:
    """
    Validate Python source code strictly preserving valid code syntax:
    - Rejects non-string types.
    - Rejects empty or whitespace-only code.
    - Rejects code containing embedded null bytes.
    - Normalizes Unicode safely.
    - Enforces maximum byte size (default 64 KiB).
    - PRESERVES quotes (', "), brackets ((), [], {}), operators (+, -, *, /, <, >, =, &),
      and backticks/fences (```) exactly.
    """
    if not isinstance(code, str):
        raise TypeError(f"Source code must be a string, got {type(code).__name__}.")

    if has_null_bytes(code):
        raise ValueError("Source code contains invalid null bytes (\\x00).")

    cleaned = code.strip()
    if not cleaned:
        raise ValueError("Source code must not be empty or whitespace-only.")

    # Safe Unicode normalization
    safe_code = normalize_unicode(code)

    encoded_bytes = safe_code.encode("utf-8")
    if len(encoded_bytes) > max_bytes:
        raise ValueError(
            f"Source code size ({len(encoded_bytes)} bytes) exceeds "
            f"the maximum allowed limit of {max_bytes} bytes ({max_bytes // 1024} KiB)."
        )

    return safe_code


def validate_filename_label(filename: str, max_length: int = MAX_FILENAME_CHARS) -> str:
    """
    Validate that a filename is a simple display label.
    Rejects directory separators, path traversal, drive letters, and null bytes.
    """
    if not isinstance(filename, str):
        raise TypeError(f"Filename must be a string, got {type(filename).__name__}.")

    if has_null_bytes(filename):
        raise ValueError("Filename contains invalid null bytes.")

    cleaned = strip_unsafe_control_characters(normalize_unicode(filename.strip()), keep_newlines=False)
    if not cleaned:
        raise ValueError("Filename must not be empty or whitespace-only.")

    if len(cleaned) > max_length:
        raise ValueError(f"Filename exceeds maximum allowed length of {max_length} characters.")

    # Check for path traversal components
    if (
        ".." in cleaned
        or "/" in cleaned
        or "\\" in cleaned
        or (len(cleaned) > 1 and cleaned[1] == ":")
    ):
        raise ValueError(
            f"Invalid filename '{filename}': filename must be a simple display label "
            "and cannot contain directory separators, drive letters, or path traversal components."
        )

    return cleaned


def validate_slug(slug: str, max_length: int = MAX_SLUG_CHARS) -> str:
    """Validate that a problem or entity slug contains only lowercase alphanumeric, dashes, and underscores."""
    if not isinstance(slug, str):
        raise TypeError(f"Slug must be a string, got {type(slug).__name__}.")

    cleaned = strip_null_bytes(slug).strip().lower()
    if not cleaned:
        raise ValueError("Slug must not be empty.")

    if len(cleaned) > max_length:
        raise ValueError(f"Slug exceeds maximum allowed length of {max_length} characters.")

    if not SAFE_SLUG_PATTERN.match(cleaned):
        raise ValueError(
            f"Invalid slug '{slug}': must contain only lowercase alphanumeric characters, dashes, and underscores."
        )

    return cleaned


def validate_tool_name(name: str) -> str:
    """Validate that a tool name is a valid identifier."""
    if not isinstance(name, str):
        raise TypeError(f"Tool name must be a string, got {type(name).__name__}.")

    cleaned = strip_null_bytes(name).strip()
    if not cleaned:
        raise ValueError("Tool name must not be empty.")

    if not SAFE_TOOL_NAME_PATTERN.match(cleaned):
        raise ValueError(
            f"Invalid tool name '{name}': must be an alphanumeric identifier containing only letters, numbers, and underscores."
        )

    return cleaned


def validate_uuid_format(val: Any, field_name: str = "id") -> Optional[uuid.UUID]:
    """Validate and convert an input into a valid UUID object."""
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return val
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None
        try:
            return uuid.UUID(cleaned)
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid {field_name} '{val}': must be a valid RFC 4122 UUID.")
    raise TypeError(f"Expected {field_name} as UUID or UUID string, got {type(val).__name__}.")


def sanitize_problem_context_dict(
    context: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Sanitize and bound problem context metadata:
    - Bounding title, slug, and description.
    - Stripping null bytes and unsafe controls.
    - Limiting constraint count and length.
    - Validating parameters list.
    """
    if context is None:
        return None

    if not isinstance(context, dict):
        raise TypeError("problem_context must be a dictionary.")

    sanitized: Dict[str, Any] = {}

    if "title" in context and context["title"] is not None:
        sanitized["title"] = sanitize_text(str(context["title"]), max_length=MAX_TITLE_CHARS, allow_newlines=False)

    if "slug" in context and context["slug"] is not None:
        raw_slug = str(context["slug"]).strip()
        if raw_slug:
            try:
                sanitized["slug"] = validate_slug(raw_slug)
            except ValueError:
                # If slug contains invalid chars, sanitize it into safe slug format
                safe_slug = re.sub(r"[^a-z0-9_-]", "-", raw_slug.lower())[:MAX_SLUG_CHARS].strip("-")
                sanitized["slug"] = safe_slug or "problem"

    if "description" in context and context["description"] is not None:
        sanitized["description"] = sanitize_text(
            str(context["description"]),
            max_length=MAX_PROBLEM_DESCRIPTION_CHARS,
            allow_newlines=True,
        )

    if "constraints" in context and context["constraints"] is not None:
        raw_constraints = context["constraints"]
        if isinstance(raw_constraints, list):
            cleaned_constraints = []
            for item in raw_constraints[:MAX_CONSTRAINTS_COUNT]:
                if item is not None:
                    cleaned_c = sanitize_text(str(item), max_length=MAX_CONSTRAINT_ITEM_CHARS, allow_newlines=False)
                    if cleaned_c:
                        cleaned_constraints.append(cleaned_c)
            sanitized["constraints"] = cleaned_constraints

    if "parameters" in context and context["parameters"] is not None:
        raw_params = context["parameters"]
        if isinstance(raw_params, list):
            sanitized["parameters"] = sanitize_recursive_value(raw_params[:20])

    # Copy any remaining safe primitive keys
    for k, v in context.items():
        if k not in sanitized:
            sanitized[k] = sanitize_recursive_value(v)

    return sanitized


def sanitize_recursive_value(val: Any, max_string_length: int = 10000) -> Any:
    """Recursively strip null bytes, unsafe controls, and normalize strings in nested structures."""
    if val is None or isinstance(val, (bool, int, float)):
        return val
    if isinstance(val, str):
        if has_null_bytes(val):
            val = strip_null_bytes(val)
        safe = normalize_unicode(val)
        cleaned = strip_unsafe_control_characters(safe, keep_newlines=True, keep_tabs=True)
        if len(cleaned) > max_string_length:
            cleaned = cleaned[:max_string_length]
        return cleaned
    elif isinstance(val, dict):
        cleaned_dict = {}
        for k, v in val.items():
            clean_k = strip_null_bytes(str(k)).strip()
            if clean_k:
                cleaned_dict[clean_k] = sanitize_recursive_value(v, max_string_length=max_string_length)
        return cleaned_dict
    elif isinstance(val, (list, tuple)):
        return [sanitize_recursive_value(item, max_string_length=max_string_length) for item in val[:MAX_TEST_CASES_COUNT]]
    return val


def sanitize_tool_arguments_dict(args: Any) -> Dict[str, Any]:
    """
    Validate and sanitize tool argument dictionaries recursively.

    Enforces:
    - Must be a dictionary.
    - Maximum total serialized payload size (256 KiB).
    - Maximum nesting depth (10).
    - Maximum dictionary entries (100 per dict).
    - Maximum list length (100 items per list).
    - Maximum individual string length (64 KiB).
    - Supported JSON-compatible types only (dict, list, str, int, float, bool, NoneType).
    - Null byte rejection in keys and strings.
    - Safe Unicode normalization (NFC + surrogate elimination).
    - STRICT PRESERVATION OF SOURCE CODE: preserves tabs (\\t), newlines (\\n, \\r),
      spaces, indentation, quotes, brackets, and code fences without generic text modification.

    Raises:
        TypeError: If args is not a dict or contains unsupported non-JSON types.
        ValueError: If nesting depth, dictionary size, list length, string length,
                    or total payload size limits are exceeded, or if null bytes are found.
    """
    if not isinstance(args, dict):
        raise TypeError(f"Tool arguments must be a dictionary, got {type(args).__name__}.")

    # 1. Total serialized argument payload size limit
    try:
        serialized = json.dumps(args)
    except (TypeError, ValueError) as json_err:
        raise TypeError(f"Tool arguments must be JSON-serializable: {json_err}") from json_err

    serialized_bytes = len(serialized.encode("utf-8"))
    if serialized_bytes > MAX_TOOL_ARG_TOTAL_SERIALIZED_BYTES:
        raise ValueError(
            f"Total serialized tool arguments size ({serialized_bytes} bytes) "
            f"exceeds maximum allowed limit of {MAX_TOOL_ARG_TOTAL_SERIALIZED_BYTES} bytes (256 KiB)."
        )

    # 2. Recursive traversal enforcing depth, size limits, types, and safe string preservation
    def _sanitize_recursive(val: Any, depth: int) -> Any:
        if depth > MAX_TOOL_ARG_NESTING_DEPTH:
            raise ValueError(
                f"Tool arguments exceed maximum allowed nesting depth of {MAX_TOOL_ARG_NESTING_DEPTH}."
            )

        if val is None or isinstance(val, (bool, int, float)):
            return val

        if isinstance(val, str):
            if len(val) > MAX_TOOL_ARG_STRING_LENGTH:
                raise ValueError(
                    f"Tool argument string length ({len(val)}) exceeds maximum limit of "
                    f"{MAX_TOOL_ARG_STRING_LENGTH} characters."
                )
            # Safe null byte stripping and Unicode normalization
            stripped_val = strip_null_bytes(val)
            safe_str = normalize_unicode(stripped_val)
            # Strip non-printable control characters while strictly preserving newlines (\n, \r) and tabs (\t)
            return strip_unsafe_control_characters(safe_str, keep_newlines=True, keep_tabs=True)

        if isinstance(val, dict):
            if len(val) > MAX_TOOL_ARG_DICT_ENTRIES:
                raise ValueError(
                    f"Tool argument dictionary has {len(val)} entries, exceeding maximum limit "
                    f"of {MAX_TOOL_ARG_DICT_ENTRIES}."
                )
            cleaned_dict = {}
            for k, v in val.items():
                if not isinstance(k, str):
                    raise TypeError(f"Tool argument dictionary key must be string, got {type(k).__name__}.")
                if len(k) > 255:
                    raise ValueError(f"Tool argument dictionary key exceeds 255 characters: '{k[:50]}...'")
                clean_k = strip_null_bytes(strip_unsafe_control_characters(normalize_unicode(k), keep_newlines=False, keep_tabs=False)).strip()
                if not clean_k:
                    continue
                cleaned_dict[clean_k] = _sanitize_recursive(v, depth + 1)
            return cleaned_dict

        if isinstance(val, (list, tuple)):
            if len(val) > MAX_TOOL_ARG_LIST_LENGTH:
                raise ValueError(
                    f"Tool argument list has {len(val)} items, exceeding maximum limit "
                    f"of {MAX_TOOL_ARG_LIST_LENGTH}."
                )
            return [_sanitize_recursive(item, depth + 1) for item in val]

        raise TypeError(
            f"Unsupported tool argument value type '{type(val).__name__}': "
            "only JSON-compatible types (dict, list, str, int, float, bool, None) are permitted."
        )

    return _sanitize_recursive(args, depth=0)


def redact_secrets(text: str, custom_secrets: Optional[List[str]] = None) -> str:
    """
    Redact API keys, tokens, and sensitive credentials from log and response text.
    """
    if not text:
        return ""

    sanitized = str(text)

    # 1. Redact configured custom secrets if provided
    if custom_secrets:
        for secret in custom_secrets:
            if secret and len(secret) >= 6 and secret in sanitized:
                sanitized = sanitized.replace(secret, "[REDACTED]")

    # 2. Redact database connection passwords
    sanitized = re.sub(r"://([^:]+):([^@]+)@", r"://\1:[REDACTED]@", sanitized)

    # 3. Redact Authorization Bearer tokens
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9\-_\.]+", "Bearer [REDACTED]", sanitized)

    # 4. Redact OpenAI and Google API keys: sk-proj-..., sk-..., AIza...
    sanitized = re.sub(r"(?:sk-(?:proj-)?[a-zA-Z0-9_\-]{20,}|AIza[0-9A-Za-z\-_]{30,})", "[REDACTED]", sanitized)

    # 5. Redact key-value secret pairs
    sanitized = re.sub(
        r"((?:api[_-]?key|secret[_-]?key|password|jwt[_-]?secret)\s*[:=]\s*[\"']?)([^\s,;\"']+)([\"']?)",
        r"\1[REDACTED]\3",
        sanitized,
        flags=re.IGNORECASE,
    )

    return sanitized


def redact_secrets_recursive(val: Any, custom_secrets: Optional[List[str]] = None) -> Any:
    """
    Recursively redact secrets from arbitrary nested data structures
    (dictionaries, lists, tuples, and strings).
    """
    if isinstance(val, str):
        return redact_secrets(val, custom_secrets=custom_secrets)
    if isinstance(val, dict):
        return {k: redact_secrets_recursive(v, custom_secrets=custom_secrets) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [redact_secrets_recursive(item, custom_secrets=custom_secrets) for item in val]
    return val


def escape_boundary_tags(text: str, tag: str) -> str:
    """
    Escape occurrences of closing tags inside untrusted content to prevent
    prompt injection attacks from prematurely closing structural XML boundaries.
    Example: '</untrusted_code>' becomes '&lt;/untrusted_code&gt;'.
    """
    if not text:
        return ""
    # Escape the specific closing tag and any generic untrusted closing tags
    safe = text.replace(f"</{tag}>", f"&lt;/{tag}&gt;")
    safe = safe.replace(f"<{tag}>", f"&lt;{tag}&gt;")
    # Escape generic untrusted tag closures
    safe = re.sub(r"<\s*/\s*untrusted_([a-zA-Z0-9_]+)\s*>", r"&lt;/untrusted_\1&gt;", safe, flags=re.IGNORECASE)
    return safe


def wrap_untrusted(tag: str, content: str) -> str:
    """
    Wrap untrusted content in XML enclosure tags with internal closing tag escaping.
    """
    escaped = escape_boundary_tags(content, tag)
    return f"<{tag}>\n{escaped}\n</{tag}>"


# -----------------------------------------------------------------------------
# Incremental Secret Redactor for Streaming Responses
# -----------------------------------------------------------------------------

SECRET_PREFIXES = (
    "sk-", "sk", "AIza", "AIz", "AI",
    "Bearer", "bearer",
    "://", "postgres", "mysql", "http",
    "api_key", "apikey", "secret_key", "password", "jwt_secret",
)


class StreamSecretBuffer:
    """
    Incremental secret redactor for token streams.
    Prevents leaking credentials that span across chunk boundaries by buffering
    potential secret candidates until a boundary delimiter is reached or flushed.
    """

    def __init__(self, custom_secrets: Optional[List[str]] = None):
        self._custom_secrets = [s for s in (custom_secrets or []) if s and len(s) >= 4]
        self._buffer: str = ""

    def _is_potential_secret_prefix(self, token: str) -> bool:
        if not token:
            return False
        lower_token = token.lower()
        for p in SECRET_PREFIXES:
            if p.lower().startswith(lower_token) or lower_token.startswith(p.lower()):
                return True
        for cs in self._custom_secrets:
            if cs.startswith(token) or token.startswith(cs):
                return True
        return False

    def push(self, chunk: str) -> str:
        """
        Push an incremental stream chunk into the buffer.
        Returns safe, redacted text ready for client emission,
        holding incomplete words or potential secret candidates.
        """
        if not chunk:
            return ""
        self._buffer += chunk

        # Look for the last whitespace delimiter
        last_space_idx = -1
        for idx in range(len(self._buffer) - 1, -1, -1):
            if self._buffer[idx] in (" ", "\t", "\n", "\r"):
                last_space_idx = idx
                break

        if last_space_idx == -1:
            if len(self._buffer) > 256:
                redacted = redact_secrets(self._buffer, custom_secrets=self._custom_secrets)
                to_emit = redacted[:-64]
                self._buffer = self._buffer[-64:]
                return to_emit
            return ""

        current_word = self._buffer[last_space_idx + 1:]
        prefix_to_check = self._buffer[:last_space_idx].split()
        prev_word = prefix_to_check[-1] if prefix_to_check else ""

        if prev_word.lower() in ("bearer", "password:", "api_key:", "secret_key:") or self._is_potential_secret_prefix(current_word):
            if prev_word.lower() in ("bearer", "password:", "api_key:", "secret_key:"):
                cut_idx = self._buffer[:last_space_idx].rfind(prev_word)
                if cut_idx > 0:
                    ready_text = self._buffer[:cut_idx]
                    self._buffer = self._buffer[cut_idx:]
                    return redact_secrets(ready_text, custom_secrets=self._custom_secrets)
                return ""
            else:
                ready_text = self._buffer[:last_space_idx + 1]
                self._buffer = self._buffer[last_space_idx + 1:]
                return redact_secrets(ready_text, custom_secrets=self._custom_secrets)

        ready_text = self._buffer[:last_space_idx + 1]
        self._buffer = self._buffer[last_space_idx + 1:]
        return redact_secrets(ready_text, custom_secrets=self._custom_secrets)

    def flush(self) -> str:
        """
        Flush and redact all remaining buffered content at the end of the stream.
        """
        if not self._buffer:
            return ""
        redacted = redact_secrets(self._buffer, custom_secrets=self._custom_secrets)
        self._buffer = ""
        return redacted
