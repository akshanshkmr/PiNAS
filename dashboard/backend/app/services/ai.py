"""Local vision model client (OpenAI-compatible /v1/chat/completions).

Backend-agnostic: talks to Ollama, LM Studio, or any OpenAI-compatible endpoint
that supports vision. Config is a URL + model name; the request format is the
standard multimodal chat schema.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from .files import HEIF_EXT, heic_to_jpeg, resolve

# runtime config (kept in-process; persisted via /ai/config → env-backed store)
_DEFAULT_BASE = os.environ.get("AI_BASE_URL", "http://127.0.0.1:11434/v1")
_DEFAULT_MODEL = os.environ.get("AI_MODEL", "moondream")

# lazy Pillow — the /raw route already imports it, but keep this module usable
# if pillow ever isn't available at import time.
try:
    from PIL import Image
    _PIL_OK = True
except Exception:  # pragma: no cover
    _PIL_OK = False

MAX_EDGE = 768  # downscale for the model; smaller = faster on CPU

PROMPT = (
    "Describe this image in 2 to 3 short sentences — the subjects, what they are "
    "doing, the setting, and the mood. Use concrete nouns."
)

# Words we don't want as tags (very small, deliberately English-only).
_STOPWORDS = frozenset(
    """
    a an and any are as at be been being both but by can could did do does doing
    down during each few for from further had has have having he her here hers herself
    him himself his how i in into is it its itself just just me might more most my
    myself no nor not now of off on once only or other our ours ourselves out over
    own said same seems she should so some such than that the their theirs them
    themselves then there these they this those through to too under until up
    upon us very was we were what when where which while who whom why will with
    would you your yours yourself yourselves image photo picture scene shows show
    showing appears seem seems seemed suggests suggest indicates indicate look
    looks looking one two three thing things person people someone something anyone
    everyone attending held holding creates create creating warm loving especially
    together really likely
    """.split()
)


def _tags_from_caption(caption: str, max_tags: int = 10) -> list[str]:
    """Pull meaningful tags out of the caption: lowercase, no stopwords,
    length 3+, first-occurrence order preserved."""
    words = re.findall(r"[A-Za-z][A-Za-z\-']{2,}", caption.lower())
    seen: list[str] = []
    for w in words:
        if w in _STOPWORDS or len(w) < 3:
            continue
        if w not in seen:
            seen.append(w)
        if len(seen) >= max_tags:
            break
    return seen


@dataclass
class AIConfig:
    base_url: str = _DEFAULT_BASE
    model: str = _DEFAULT_MODEL

    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"


_config = AIConfig()


def get_config() -> AIConfig:
    return _config


def set_config(base_url: str | None = None, model: str | None = None) -> AIConfig:
    if base_url:
        _config.base_url = base_url.strip()
    if model:
        _config.model = model.strip()
    return _config


async def health() -> dict:
    """Check that the endpoint responds and the model is loadable."""
    url = _config.base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return {"ok": False, "error": f"models endpoint returned HTTP {r.status_code}"}
        data = r.json()
        models = [m.get("id") for m in data.get("data", [])]
        # Ollama tags a model like "moondream:latest"; accept a bare match too
        wanted = _config.model
        available = wanted in models or any(
            m == wanted or m.split(":")[0] == wanted for m in models if m
        )
        return {
            "ok": True,
            "base_url": _config.base_url,
            "model": _config.model,
            "model_available": available,
            "models": models,
        }
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"cannot reach {url}: {e}"}


def _load_image_bytes(path: str) -> bytes:
    """Return a downscaled JPEG for the given path (HEIC transcoded)."""
    if not _PIL_OK:
        raise RuntimeError("Pillow is not installed on the server.")
    target = resolve(path)
    if not target.is_file():
        raise FileNotFoundError("Not a file.")

    # HEIC path: reuse the transcoder, then re-open to downscale further.
    if target.suffix.lower() in HEIF_EXT:
        jpeg = heic_to_jpeg(path)
        im = Image.open(io.BytesIO(jpeg))
    else:
        im = Image.open(target)
    with im:
        im = im.convert("RGB")
        im.thumbnail((MAX_EDGE, MAX_EDGE))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        return buf.getvalue()


def _extract_json(text: str) -> dict | None:
    """Parse the model's response — tolerant of code fences and prose."""
    text = text.strip()
    # strip ``` fences
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    # first {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def _chat(prompt: str, image_b64: str, timeout: float) -> str:
    body = {
        "model": _config.model,
        "temperature": 0.2,
        "max_tokens": 400,  # avoid truncated captions on small models
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }
        ],
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(_config.chat_url(), json=body)
    if r.status_code != 200:
        raise RuntimeError(f"vision model returned HTTP {r.status_code}: {r.text[:200]}")
    payload = r.json()
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"unexpected response shape: {str(payload)[:200]}")


def _parse_tag_list(text: str) -> list[str]:
    """Turn a comma / newline / bullet list into normalized lowercase tags."""
    out: list[str] = []
    # strip common list markers, split on comma or newline
    text = re.sub(r"^\s*[-*•\d\.\)]+\s*", "", text, flags=re.MULTILINE)
    for chunk in re.split(r"[,\n]+", text):
        s = chunk.strip().lower().strip(" .;:\"'`")
        # drop obvious sentence fragments
        if not s or len(s) > 40 or " " in s and len(s.split()) > 4:
            continue
        if s not in out:
            out.append(s)
    return out[:12]


async def describe_image(path: str, timeout: float = 180.0) -> dict:
    """Run the vision model on `path`. Returns {caption, tags, raw}.

    One call to the vision model for a natural-language caption; tags are
    derived from the caption (see `_tags_from_caption`) — small models like
    moondream don't reliably follow "reply as JSON" or "list tags only"
    instructions, but they are excellent captioners.
    """
    img = _load_image_bytes(path)
    b64 = base64.b64encode(img).decode("ascii")

    raw = await _chat(PROMPT, b64, timeout)
    caption = raw.strip()[:400]
    tags = _tags_from_caption(caption)
    return {"caption": caption, "tags": tags, "raw": raw}
