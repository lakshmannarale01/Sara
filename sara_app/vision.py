"""Explicit, ephemeral image input for a verified local Ollama vision model.

REST payloads use base64 image bytes, as documented at
https://docs.ollama.com/capabilities/vision and /api/generate.
This module never captures hardware, writes images, or uploads them to cloud AI.
"""
import base64
import binascii
import io
import json
import os
import threading
import time
import warnings
from urllib.parse import urlparse
import urllib.request

from .config import OLLAMA_MODEL, OLLAMA_URL

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = ImageOps = None

MAX_ATTACHMENTS = 4
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_EDGE = 1920
_MIME_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
_SOURCES = {"upload", "screen", "camera"}
_status_lock = threading.Lock()
_status_cache = {"until": 0.0, "key": None, "value": None}


def validate_attachments(raw):
    """Decode/re-encode bounded raster images; never trust client metadata.

    Returning JPEG strips EXIF/location metadata and bounds image dimensions.
    Callers must not persist or log the returned data_url/base64 values.
    """
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_ATTACHMENTS:
        raise ValueError("Attach at most four images in one message.")
    if not raw:
        return []
    if Image is None:
        raise ValueError("Image support needs Pillow. Install the updated requirements and restart SARA.")
    normalized, total = [], 0
    for attachment in raw:
        if not isinstance(attachment, dict):
            raise ValueError("Each attachment must contain a PNG, JPEG or WebP image.")
        source = attachment.get("source", "upload")
        if source not in _SOURCES:
            raise ValueError("Unknown image source; choose upload, screen or camera.")
        data_url = attachment.get("data_url")
        if not isinstance(data_url, str) or "," not in data_url:
            raise ValueError("Use an attached image, not a file path or remote URL.")
        header, encoded = data_url.split(",", 1)
        mime = header.removeprefix("data:").removesuffix(";base64")
        if header != "data:" + mime + ";base64" or mime not in _MIME_FORMATS:
            raise ValueError("Supported image formats are PNG, JPEG and WebP.")
        if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
            raise ValueError("Images must total at most 10 MB per message.")
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("The attached image has invalid base64 data.") from exc
        total += len(image_bytes)
        if not image_bytes or total > MAX_IMAGE_BYTES:
            raise ValueError("Images must total at most 10 MB per message.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(image_bytes)) as probe:
                    if probe.format != _MIME_FORMATS[mime]:
                        raise ValueError("Image contents do not match the selected format.")
                    if probe.width < 1 or probe.height < 1 or probe.width * probe.height > MAX_PIXELS:
                        raise ValueError("Images must contain at most 16 million pixels.")
                    if getattr(probe, "n_frames", 1) != 1:
                        raise ValueError("Attach a still image rather than an animated image.")
                    probe.verify()
                with Image.open(io.BytesIO(image_bytes)) as opened:
                    opened.load()
                    oriented = ImageOps.exif_transpose(opened)
                    oriented.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
                    rgb = Image.new("RGB", oriented.size, "white")
                    if "A" in oriented.getbands():
                        rgba = oriented.convert("RGBA")
                        rgb.paste(rgba, mask=rgba.getchannel("A"))
                    else:
                        rgb.paste(oriented.convert("RGB"))
                    output = io.BytesIO()
                    rgb.save(output, format="JPEG", quality=88)
                    width, height = rgb.size
            clean = base64.b64encode(output.getvalue()).decode("ascii")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("The image is damaged or cannot be decoded. Attach a valid PNG, JPEG or WebP.") from exc
        normalized.append({"data_url": "data:image/jpeg;base64," + clean,
                           "base64": clean, "source": source, "mime": "image/jpeg",
                           "width": width, "height": height})
    return normalized


def attachment_summary(attachments):
    """Safe metadata only, suitable for history records and action context."""
    return [{"source": item["source"], "width": item["width"], "height": item["height"]}
            for item in attachments]


def _local_endpoint():
    parsed = urlparse(OLLAMA_URL)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _json_request(path, payload=None, timeout=1.5):
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(OLLAMA_URL.rstrip("/") + path, data=body,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        # Model metadata is small; do not accept an unbounded provider response.
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Ollama model metadata was too large.")
        value = json.loads(data.decode())
        if not isinstance(value, dict):
            raise ValueError("Invalid Ollama model metadata.")
        return value


def vision_status(force=False):
    """Discover actual vision capability without downloading/loading a model."""
    preferred = os.getenv("SARA_VISION_MODEL", "").strip()
    key = (OLLAMA_URL, OLLAMA_MODEL, preferred, Image is not None)
    with _status_lock:
        if not force and key == _status_cache["key"] and time.monotonic() < _status_cache["until"]:
            return dict(_status_cache["value"])
        result = {"available": False, "provider": "local-ollama", "model": None,
                  "models": [], "decoder_available": Image is not None,
                  "max_attachments": MAX_ATTACHMENTS, "max_total_bytes": MAX_IMAGE_BYTES,
                  "images_saved": False, "cloud_upload": False}
        if Image is None:
            result["reason"] = "Install updated requirements (Pillow), then restart SARA for image support."
        elif not _local_endpoint():
            result["reason"] = "Images stay local. Configure SARA_OLLAMA_URL to a local Ollama service."
        else:
            try:
                listed = _json_request("/api/tags").get("models", [])
                installed = [item for item in listed if isinstance(item, dict) and isinstance(item.get("name", item.get("model")), str)] if isinstance(listed, list) else []
                def score(item):
                    name = item.get("name", item.get("model"))
                    aliases = {name, name.removesuffix(":latest")}
                    rank = 0 if preferred and preferred in aliases else 1 if OLLAMA_MODEL in aliases else 2
                    size = item.get("size", 0)
                    return rank, size if isinstance(size, (float, int)) else 0
                installed.sort(key=score)
                deadline = time.monotonic() + 7
                for item in installed[:12]:
                    if time.monotonic() >= deadline:
                        break
                    name = item.get("name", item.get("model"))
                    try:
                        info = _json_request("/api/show", {"model": name}, timeout=min(1.5, max(.1, deadline - time.monotonic())))
                    except Exception:
                        continue
                    capabilities = info.get("capabilities", [])
                    if isinstance(capabilities, list) and "vision" in capabilities:
                        result["models"].append(name)
                        result.update(available=True, model=name)
                        # The preferred/first eligible installed model is enough.
                        break
                result["reason"] = ("Ready: images are processed by the installed local vision model."
                                    if result["available"] else
                                    "No installed vision-capable Ollama model was found. Install one (for example: ollama pull llava), then refresh. Text-only llama3.2 cannot see images.")
            except Exception:
                result["reason"] = "Local Ollama is not reachable. Start Ollama and install a vision-capable model, then refresh."
        _status_cache.update(key=key, value=result, until=time.monotonic() + (60 if result["available"] else 5))
        return dict(result)


def unavailable_reply(message, status=None):
    status = status or vision_status()
    if any(word in str(message).casefold() for word in ("hai", "kya", "mujhe", "dekho", "batao")) or any("\u0900" <= letter <= "\u097f" for letter in str(message)):
        return "इस image को समझने के लिए local vision model तैयार नहीं है। " + status["reason"] + " मैंने image देखकर कोई निष्कर्ष नहीं निकाला है।"
    return "I could not inspect this image. " + status["reason"]
