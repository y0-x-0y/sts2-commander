"""LLMClient — LLM 调用的封装层。

隔离 LLM 调用细节（CLI/API/模型选择），其他模块只需：
    result = self.llm.ask(prompt)
"""

import os
import shutil
import subprocess

from overlay.constants import LLM_CLI, SYSTEM_PROMPT_FILE


class LLMClient:
    """LLM 客户端 — 封装 Claude CLI 调用。

    用法：
        self.llm = LLMClient()
        answer = self.llm.ask("分析这个战斗...")
        answer = self.llm.ask(prompt, timeout=90)
    """

    def __init__(self, post_process=None):
        """
        Args:
            post_process: 可选的后处理函数 (str) -> str，
                          如 CardDB.translate 用于翻译英文卡名。
        """
        self._cli = LLM_CLI
        self._system_prompt = None  # 懒加载，缓存
        self._post_process = post_process

        if not shutil.which(self._cli):
            print(f"[LLM] Warning: CLI '{self._cli}' not found")

    def ask(self, prompt: str, timeout: int = 60) -> str:
        """调用 LLM，返回回答文本。

        Raises:
            RuntimeError: CLI 不存在、超时、或返回错误
        """
        if not os.path.exists(self._cli) and not shutil.which(self._cli):
            raise RuntimeError(f"LLM 未找到：{self._cli}\n请检查 config.json 中的 llm_cli 路径")

        cmd = [self._cli, "--print", "--permission-mode", "bypassPermissions"]

        # 懒加载 system prompt
        if self._system_prompt is None:
            self._system_prompt = self._load_system_prompt()
        if self._system_prompt:
            cmd += ["--system-prompt", self._system_prompt]

        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True,
                               text=True, timeout=timeout)
        except FileNotFoundError:
            raise RuntimeError(f"LLM 无法执行：{self._cli}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("分析超时，请重试")

        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "调用失败")

        result = r.stdout.strip()

        # 后处理（如英文→中文翻译）
        if self._post_process:
            result = self._post_process(result)

        return result

    @property
    def available(self) -> bool:
        """LLM CLI 是否可用。"""
        return bool(shutil.which(self._cli))

    @staticmethod
    def _load_system_prompt() -> str:
        """加载 system prompt 文件。"""
        try:
            if os.path.exists(SYSTEM_PROMPT_FILE):
                with open(SYSTEM_PROMPT_FILE) as f:
                    return f.read().strip()
        except Exception:
            pass
        return ""
