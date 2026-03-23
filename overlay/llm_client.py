"""LLMClient — LLM call abstraction.

Supports two backends:
  1. CLI mode (default): calls claude/llm CLI via subprocess
  2. API mode: calls OpenAI-compatible API (Anthropic, OpenAI, local, etc.)

Config via config.json:
  CLI mode:  {"llm_cli": "/path/to/claude"}
  API mode:  {"llm_api_base": "https://api.anthropic.com/v1", "llm_model": "claude-sonnet-4-20250514"}
  API key:   set env var LLM_API_KEY (never stored in config/code)
"""

import os
import shutil
import subprocess
import json

from overlay.constants import LLM_CLI, _proj

SYSTEM_PROMPT_FILE = _proj("docs", "system_prompt.txt")

# Load API config from config.json if present
_CONFIG_PATH = _proj("config.json")
_CONFIG = {}
try:
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            _CONFIG = json.load(f)
except Exception:
    pass


class LLMClient:
    """LLM client — abstracts CLI and API backends."""

    def __init__(self, post_process=None):
        self._post_process = post_process
        self._system_prompt = None

        # Determine backend
        self._api_base = _CONFIG.get("llm_api_base", "")
        self._model = _CONFIG.get("llm_model", "")
        self._api_key = os.environ.get("LLM_API_KEY", "")
        self._cli = LLM_CLI

        if self._api_base and self._api_key:
            self._mode = "api"
            print(f"[LLM] API mode: {self._api_base} model={self._model}")
        else:
            self._mode = "cli"
            if not shutil.which(self._cli):
                print(f"[LLM] Warning: CLI '{self._cli}' not found")
            else:
                print(f"[LLM] CLI mode: {self._cli}")

    def ask(self, prompt: str, timeout: int = 60) -> str:
        """Call LLM and return response text."""
        if self._mode == "api":
            result = self._ask_api(prompt, timeout)
        else:
            result = self._ask_cli(prompt, timeout)

        if self._post_process:
            result = self._post_process(result)
        return result

    def _ask_cli(self, prompt: str, timeout: int) -> str:
        if not os.path.exists(self._cli) and not shutil.which(self._cli):
            raise RuntimeError(f"LLM not found: {self._cli}")

        cmd = [self._cli, "--print", "--permission-mode", "bypassPermissions"]

        if self._system_prompt is None:
            self._system_prompt = self._load_system_prompt()
        if self._system_prompt:
            cmd += ["--system-prompt", self._system_prompt]

        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True,
                               text=True, timeout=timeout)
        except FileNotFoundError:
            raise RuntimeError(f"LLM cannot execute: {self._cli}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Analysis timeout, please retry")

        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "LLM call failed")

        return r.stdout.strip()

    def _ask_api(self, prompt: str, timeout: int) -> str:
        import requests

        if self._system_prompt is None:
            self._system_prompt = self._load_system_prompt()

        headers = {"Content-Type": "application/json"}
        messages = []

        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Detect API format (Anthropic vs OpenAI)
        if "anthropic" in self._api_base.lower():
            # Anthropic Messages API
            headers["x-api-key"] = self._api_key
            headers["anthropic-version"] = "2023-06-01"
            body = {
                "model": self._model or "claude-sonnet-4-20250514",
                "max_tokens": 2048,
                "system": self._system_prompt or "",
                "messages": [{"role": "user", "content": prompt}],
            }
            url = self._api_base.rstrip("/") + "/messages"
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return data.get("content", [{}])[0].get("text", "").strip()
        else:
            # OpenAI-compatible API (OpenAI, local, etc.)
            headers["Authorization"] = f"Bearer {self._api_key}"
            body = {
                "model": self._model or "gpt-4",
                "messages": messages,
                "max_tokens": 2048,
            }
            url = self._api_base.rstrip("/") + "/chat/completions"
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()

    @property
    def available(self) -> bool:
        if self._mode == "api":
            return bool(self._api_base and self._api_key)
        return bool(shutil.which(self._cli))

    @staticmethod
    def _load_system_prompt() -> str:
        try:
            if os.path.exists(SYSTEM_PROMPT_FILE):
                with open(SYSTEM_PROMPT_FILE) as f:
                    return f.read().strip()
        except Exception:
            pass
        return ""
