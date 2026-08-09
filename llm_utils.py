"""
OpenAI 兼容的 LLM 调用封装
==========================
支持任何 OpenAI 兼容端点：OpenAI / DeepSeek / Moonshot / 本地 Ollama 等。

环境变量:
  LLM_BASE_URL  - API base，默认 https://api.openai.com/v1
                  DeepSeek: https://api.deepseek.com/v1
                  Moonshot: https://api.moonshot.cn/v1
                  Ollama:   http://localhost:11434/v1
  LLM_API_KEY   - API key
  LLM_MODEL     - 模型名，默认 gpt-4o-mini
"""
from __future__ import annotations

import json
import os
from typing import Any

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # 延迟到真正调用时报错

_client = None


def _get_client():
    global _client
    if OpenAI is None:
        raise RuntimeError("未安装 openai 包，请: pip install openai")
    if _client is None:
        _client = OpenAI(
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("LLM_API_KEY", "sk-no-key"),
        )
    return _client


def call_llm(system: str, user: str, temperature: float = 0.3,
             max_tokens: int = 1500) -> str:
    """调用 LLM，返回纯文本。"""
    client = _get_client()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


def call_llm_json(system: str, user: str, **kw) -> tuple[Any, str]:
    """调用 LLM 并解析 JSON 输出，返回 (parsed, raw_text)。"""
    raw = call_llm(system, user, **kw)
    s = raw.strip()
    # 去掉 ```json ... ``` 包裹
    if s.startswith("```"):
        parts = s.split("```")
        s = parts[1] if len(parts) > 1 else s
        if s.lower().startswith("json"):
            s = s[4:]
    # 截取首个 { 到末尾 } 之间内容（容错）
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    try:
        return json.loads(s), raw
    except json.JSONDecodeError as e:
        print(f"[warn] LLM JSON 解析失败: {e}\n原始: {raw[:200]}")
        return None, raw
