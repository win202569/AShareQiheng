"""Pure range-source configuration syntax, independent of registry authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType


_SOURCES = frozenset({"cninfo", "sse", "szse", "bse", "csrc"})
_EXCHANGES = frozenset({"SH", "SZ", "BJ"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_VERSION_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
_PLACEHOLDERS = frozenset(
    {"security_id", "exchange", "start_date", "end_date", "page_index"}
)
_RANGE_FIELDS = (
    "schema_version",
    "capability",
    "kind",
    "anchor_descriptor_id",
    "calendar_descriptor_id",
    "source",
    "dataset",
    "endpoint_url",
    "http_method",
    "parser_id",
    "parser_version",
    "mapping_version",
    "normalizer_version",
    "request_version",
    "exchange_scope",
    "calendar_anchor_selector",
    "request_template",
    "pagination",
    "max_pages",
    "max_calendar_days_per_request",
    "timeout_seconds",
    "retry_base_seconds",
    "retry_max_attempts",
    "challenge_cooldown_seconds",
)
_RANGE_FIELD_SET = frozenset(_RANGE_FIELDS)
_CONTEXT_SELECTOR_FIELDS = frozenset(
    {
        "kind",
        "descriptor_id",
        "context_kind",
        "scope_key",
        "field",
        "entry_id",
        "expected_type",
        "expected_unit",
    }
)
def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _text(value: object, label: str, *, version: bool = False) -> str:
    pattern = _VERSION_IDENTIFIER if version else _IDENTIFIER
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{label} must be an exact identifier")
    return value


def _hash(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _exchange(value: object, label: str = "exchange") -> str:
    if type(value) is not str or value not in _EXCHANGES:
        raise ValueError(f"{label} must be SH, SZ, or BJ")
    return value


def _positive_number(value: object, label: str) -> int | float:
    if (
        type(value) not in (int, float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{label} must be a positive finite number")
    return value


def _positive_integer(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _https_url(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be an absolute HTTPS URL")
    if any(ord(char) <= 0x20 or ord(char) == 0x7F or char.isspace() for char in value):
        raise ValueError(f"{label} contains forbidden whitespace or controls")
    if not value[:8].lower() == "https://" or "#" in value:
        raise ValueError(f"{label} must be an absolute HTTPS URL without a fragment")
    authority = value[8:].split("/", 1)[0].split("?", 1)[0]
    if not authority or "@" in authority or authority.startswith("[") or authority.count(":") > 1:
        raise ValueError(f"{label} hostname is invalid")
    host, separator, port = authority.partition(":")
    if not host or (separator and (not port or not port.isascii() or not port.isdecimal())):
        raise ValueError(f"{label} hostname or port is invalid")
    return value


def _placeholder_text(value: object, label: str, *, nonempty: bool = False) -> str:
    if type(value) is not str or value != value.strip() or (nonempty and not value):
        raise ValueError(f"{label} must be an already-trimmed string")
    remaining = _PLACEHOLDER.sub("", value)
    if "{" in remaining or "}" in remaining:
        raise ValueError(f"{label} has an invalid placeholder")
    if any(match.group(1) not in _PLACEHOLDERS for match in _PLACEHOLDER.finditer(value)):
        raise ValueError(f"{label} has an unknown placeholder")
    return value


def _template_tree(value: object, label: str, seen: set[int]) -> object:
    if value is None:
        return None
    if type(value) is str:
        _placeholder_text(value, label)
        return value
    if type(value) is list:
        if id(value) in seen:
            raise ValueError("range request template aliases or cycles are forbidden")
        seen.add(id(value))
        return [_template_tree(item, label, seen) for item in value]
    if type(value) is dict:
        if id(value) in seen:
            raise ValueError("range request template aliases or cycles are forbidden")
        seen.add(id(value))
        result = {}
        for key, item in value.items():
            _placeholder_text(key, f"{label} key", nonempty=True)
            result[key] = _template_tree(item, label, seen)
        return result
    raise ValueError(f"{label} must be a JSON mapping/list/string/null tree")


def _request_template(value: object, method: str, kind: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != {"query", "headers", "body"}:
        raise ValueError("request_template must contain exactly query, headers, and body")
    if type(value["query"]) is not dict or type(value["headers"]) is not dict:
        raise ValueError("request_template query and headers must be exact objects")
    for part in ("query", "headers"):
        for key, item in value[part].items():
            _placeholder_text(key, f"range {part} key", nonempty=True)
            _placeholder_text(item, f"range {part} value")
            if _PLACEHOLDER.search(key) or any(
                ord(char) < 0x20 or ord(char) == 0x7F or char.isspace()
                for char in key
            ):
                raise ValueError(f"range {part} key is unsafe")
            if any(
                ord(char) < 0x20 or ord(char) == 0x7F
                or (part == "query" and char.isspace())
                for char in item
            ):
                raise ValueError(f"range {part} value contains forbidden controls or whitespace")
    copied = _template_tree(value, "request_template", set())
    assert type(copied) is dict
    placeholders = {
        match.group(1)
        for text in _walk_strings(copied)
        for match in _PLACEHOLDER.finditer(text)
    }
    if kind == "calendar_range" and "security_id" in placeholders:
        raise ValueError("calendar range template cannot use security_id")
    if method == "GET" and copied["body"] is not None:
        raise ValueError("GET request_template body must be null")
    for key, item in copied["query"].items():
        if _PLACEHOLDER.search(key) or any(char in item for char in ("&", "#")):
            raise ValueError("range query template is unsafe")
    for key, item in copied["headers"].items():
        if _PLACEHOLDER.search(key) or re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", key) is None:
            raise ValueError("range header template is unsafe")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in item):
            raise ValueError("range header template contains controls")
    return copied


def _walk_strings(value: object):
    if type(value) is str:
        yield value
    elif type(value) is list:
        for item in value:
            yield from _walk_strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk_strings(item)


def _context_selector(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != _CONTEXT_SELECTOR_FIELDS:
        raise ValueError("policy calendar selector has unknown or missing keys")
    result = dict(value)
    if result["kind"] != "context" or result["context_kind"] != "trading_calendar":
        raise ValueError("policy calendar selector must identify trading_calendar Context")
    _hash(result["descriptor_id"], "policy calendar descriptor_id")
    for field in ("scope_key", "field", "expected_type"):
        _text(result[field], f"policy calendar {field}")
    for field in ("entry_id", "expected_unit"):
        if result[field] is not None:
            _text(result[field], f"policy calendar {field}")
    return result


def _bridge(value: object, kind: str, exchange: str) -> dict[str, object] | None:
    if kind == "calendar_range":
        if value is not None:
            raise ValueError("calendar range calendar_anchor_selector must be null")
        return None
    if type(value) is not dict or set(value) != {"selector", "exchange"}:
        raise ValueError("market range calendar_anchor_selector has invalid keys")
    bridge_exchange = _exchange(value["exchange"], "calendar anchor exchange")
    if bridge_exchange != exchange:
        raise ValueError("calendar anchor exchange must match exchange_scope")
    return {"selector": _context_selector(value["selector"]), "exchange": bridge_exchange}


def _freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_thaw(item) for item in value]
    return value


def _build_range_format():
    # Capture the genuine constructor in the parser and serializer closures.
    @dataclass(frozen=True, init=False)
    class RangeConfig:
        schema_version: str
        capability: str
        kind: str
        anchor_descriptor_id: str
        calendar_descriptor_id: str
        source: str
        dataset: str
        endpoint_url: str
        http_method: str
        parser_id: str
        parser_version: str
        mapping_version: str
        normalizer_version: str
        request_version: str
        exchange_scope: str
        calendar_anchor_selector: Mapping[str, object] | None
        request_template: Mapping[str, object]
        pagination: str
        max_pages: int
        max_calendar_days_per_request: int
        timeout_seconds: int | float
        retry_base_seconds: int | float
        retry_max_attempts: int
        challenge_cooldown_seconds: int | float

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("RangeConfig must be constructed by parse_range_entry")

        def to_dict(self) -> dict[str, object]:
            return _range_config_to_dict(self)

        @property
        def entry_id(self) -> str:
            return hashlib.sha256(_canonical(_range_config_to_dict(self))).hexdigest()


    def _range_config_to_dict(config: object) -> dict[str, object]:
        if type(config) is not RangeConfig:
            raise ValueError("exact RangeConfig required")
        return {
            field: _thaw(object.__getattribute__(config, field)) for field in _RANGE_FIELDS
        }


    def parse_range_entry(wire: dict) -> RangeConfig:
        """Parse one independent, closed range configuration ENTRY."""
        if type(wire) is not dict or set(wire) != _RANGE_FIELD_SET:
            raise ValueError("range config has unknown or missing keys")
        if wire["schema_version"] != "formal-range-source-config-v1":
            raise ValueError("range config schema_version is invalid")
        if wire["capability"] != "verified_market_window_v1":
            raise ValueError("range config capability is invalid")
        if type(wire["kind"]) is not str or wire["kind"] not in {"calendar_range", "market_range"}:
            raise ValueError("range config kind is invalid")
        kind = wire["kind"]
        _hash(wire["anchor_descriptor_id"], "range anchor_descriptor_id")
        _hash(wire["calendar_descriptor_id"], "range calendar_descriptor_id")
        if type(wire["source"]) is not str or wire["source"] not in _SOURCES:
            raise ValueError("range source is not an eligible official source")
        _text(wire["dataset"], "range dataset", version=True)
        _https_url(wire["endpoint_url"], "range endpoint_url")
        if type(wire["http_method"]) is not str or wire["http_method"] not in {"GET", "POST"}:
            raise ValueError("range http_method must be GET or POST")
        for field in (
            "parser_id",
            "parser_version",
            "mapping_version",
            "normalizer_version",
            "request_version",
        ):
            _text(wire[field], f"range {field}", version=True)
        if wire["request_version"] != "formal-range-request-v1":
            raise ValueError("range request_version is invalid")
        exchange = _exchange(wire["exchange_scope"], "range exchange_scope")
        bridge = _bridge(wire["calendar_anchor_selector"], kind, exchange)
        template = _request_template(wire["request_template"], wire["http_method"], kind)
        if type(wire["pagination"]) is not str or wire["pagination"] not in {
            "single_response_v1",
            "numbered_pages_v1",
        }:
            raise ValueError("range pagination is invalid")
        max_pages = _positive_integer(wire["max_pages"], "range max_pages")
        if wire["pagination"] == "single_response_v1" and max_pages != 1:
            raise ValueError("single_response_v1 requires max_pages=1")
        _positive_integer(
            wire["max_calendar_days_per_request"],
            "range max_calendar_days_per_request",
        )
        for field in (
            "timeout_seconds",
            "retry_base_seconds",
            "challenge_cooldown_seconds",
        ):
            _positive_number(wire[field], f"range {field}")
        _positive_integer(wire["retry_max_attempts"], "range retry_max_attempts")

        values = dict(wire)
        values["calendar_anchor_selector"] = bridge
        values["request_template"] = template
        result = object.__new__(RangeConfig)
        for field in _RANGE_FIELDS:
            value = values[field]
            if field in {"calendar_anchor_selector", "request_template"}:
                value = _freeze(value)
            object.__setattr__(result, field, value)
        return result

    return RangeConfig, parse_range_entry, _range_config_to_dict


RangeConfig, parse_range_entry, _range_config_to_dict = _build_range_format()
del _build_range_format

__all__ = ["RangeConfig", "parse_range_entry"]
