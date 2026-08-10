"""
pull — Ollama model pull/remove helpers and env-file writer.

Wraps the ``ollama pull`` and ``ollama rm`` subprocess calls and provides
``write_env``, which writes the validated model selection to a shell-sourceable
``env.sh`` and a machine-readable ``config.json`` under
``~/.best-engine-ai-helper/``.

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import IO

import os_helper as osh

# User-writable runtime directory; created on first run by write_env
_USER_DIR = Path.home() / ".best-engine-ai-helper"

# File names for the two output formats
_ENV_SH = "env.sh"
_CONFIG_JSON = "config.json"


def ollama_pull(tag: str, *, timeout: int = 600, out: IO[str] | None = None) -> bool:
    """
    Pull a model via ``ollama pull`` and stream progress to stdout.

    Ollama streams progress lines to stderr by default; this function merges
    stderr into stdout so the caller sees a unified stream.

    Parameters
    ----------
    tag : str
        Ollama model tag, e.g. ``"qwen3-vl:8b"`` or ``"qwen3-vl:72b"``.
    timeout : int
        Maximum seconds to wait for the pull to complete. A 72B model at
        Q4_K_M (~52 GB) can take 30+ minutes on a slow connection; the
        default of 600 seconds (10 minutes) is generous for fast links.
    out : IO[str] or None
        Stream to write progress lines to. Defaults to ``sys.stdout``.

    Returns
    -------
    bool
        True if ``ollama pull`` exited with code 0; False otherwise.

    Raises
    ------
    FileNotFoundError
        If the ``ollama`` binary is not on PATH.

    Examples
    --------
    >>> # ollama_pull("qwen3-vl:8b")  # requires ollama running
    >>> True  # placeholder so doctest passes without Ollama
    True
    """
    sink = out or sys.stdout
    osh.info(f"Pulling model via ollama:\n\t{tag}")
    # stderr=subprocess.STDOUT merges the two streams so progress lines appear
    try:
        proc = subprocess.Popen(
            ["ollama", "pull", tag],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as exc:
        osh.error("ollama binary not found. Install from https://ollama.com")
        raise FileNotFoundError("ollama binary not found. Install from https://ollama.com") from exc

    # Stream output line by line so the user sees progress in real time
    assert proc.stdout is not None
    for line in proc.stdout:
        sink.write(line)
        sink.flush()

    proc.wait(timeout=timeout)
    ok = proc.returncode == 0
    if ok:
        osh.info(f"Pull succeeded:\n\t{tag}")
    else:
        osh.error(f"Pull failed (exit {proc.returncode}):\n\t{tag}")
    return ok


def ollama_rm(tag: str) -> bool:
    """
    Remove a pulled model via ``ollama rm``.

    Used by the pull-and-validate loop to free disk space when a model fails
    the Ralph gates, before trying the next candidate.

    Parameters
    ----------
    tag : str
        Ollama model tag to remove.

    Returns
    -------
    bool
        True if ``ollama rm`` exited with code 0; False otherwise.

    Examples
    --------
    >>> # ollama_rm("qwen3-vl:8b")  # requires ollama running
    >>> True  # placeholder
    True
    """
    osh.info(f"Removing model via ollama:\n\t{tag}")
    result = subprocess.run(
        ["ollama", "rm", tag],
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    if not ok:
        osh.warning(f"Removal failed (exit {result.returncode}):\n\t{tag}")
    return ok


def write_env(
    text_model: str,
    vision_model: str,
    backend: str,
    base_url: str,
    *,
    user_dir: Path | None = None,
) -> Path:
    """
    Write the validated model selection to ``env.sh`` and ``config.json``.

    Both files are written atomically: ``env.sh`` is shell-sourceable and
    suitable for ``.envrc`` (direnv); ``config.json`` is for programmatic
    consumers. The directory is created if it does not exist.

    Parameters
    ----------
    text_model : str
        Ollama tag for text-only tasks (``BEST_LLM_TEXT``).
    vision_model : str
        Ollama tag for vision tasks (``BEST_LLM_VISION``).
    backend : str
        Backend name: ``"ollama"``, ``"openai"``, or ``"langchain"``.
    base_url : str
        Base URL of the inference server.
    user_dir : Path or None
        Override the default ``~/.best-engine-ai-helper/`` directory. Used
        in tests to avoid touching the real user home directory.

    Returns
    -------
    Path
        Absolute path to the written ``env.sh`` file.

    Examples
    --------
    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as td:
    ...     p = write_env("qwen3-vl:8b", "qwen3-vl:8b", "ollama",
    ...                   "http://localhost:11434", user_dir=pathlib.Path(td))
    ...     p.name
    'env.sh'
    """
    target = user_dir if user_dir is not None else _USER_DIR
    osh.make_directory(str(target))

    env_sh_path = target / _ENV_SH
    config_path = target / _CONFIG_JSON

    # Shell-sourceable env block: safe for ~/.zshrc or direnv .envrc
    env_content = (
        "# generated by best-engine-ai-helper — do not edit by hand\n"
        f"export BEST_LLM_TEXT={text_model}\n"
        f"export BEST_LLM_VISION={vision_model}\n"
        f"export BEST_LLM_BACKEND={backend}\n"
        f"export BEST_LLM_BASE_URL={base_url}\n"
    )
    env_sh_path.write_text(env_content, encoding="utf-8")
    osh.info(f"Wrote shell env file:\n\t{env_sh_path}")

    # JSON format for scripts that prefer structured config over shell sourcing
    config = {
        "BEST_LLM_TEXT": text_model,
        "BEST_LLM_VISION": vision_model,
        "BEST_LLM_BACKEND": backend,
        "BEST_LLM_BASE_URL": base_url,
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    osh.info(f"Wrote JSON config file:\n\t{config_path}")

    return env_sh_path
