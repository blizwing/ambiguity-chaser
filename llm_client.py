"""
DeepSeek client wrapper, ported from eval-harness's Day1_first_call.py /
Day4_json_mode.py. Only the OpenAI-schema call path is ported — per
NOTES.md (14 Sep 2026), this repo talks to DeepSeek via the `openai` SDK
pointed at DeepSeek's OpenAI-compatible endpoint, not Anthropic's schema,
so that path isn't needed here.

Requests `deepseek-flash` explicitly rather than the deprecated
`deepseek-chat` alias, per NOTES.md's DeepSeek model-change research and
this repo's carried-over P1 finding that config must always be explicit.
"""

import os
from dataclasses import dataclass

import openai
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL = "deepseek-flash"
# 1024 (eval-harness's original default, sized for a haiku) truncated a
# real TestCase response mid-field during Week 7 testing here — bumped to
# give a multi-field JSON object with a written-out ambiguity explanation
# enough room to finish.
MAX_TOKENS = 2048

OPENAI_BASE_URL = os.getenv("DEEPSEEK_OPENAI_BASE_URL", "https://api.deepseek.com")

if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY not set — check your .env")

client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url=OPENAI_BASE_URL)


@dataclass
class CallResult:
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    model_name: str


def call_deepseek_json(
    prompt: str,
    temperature: float = 0,
    model: str = MODEL,
    max_tokens: int = MAX_TOKENS,
) -> CallResult:
    """Calls DeepSeek's OpenAI-compatible endpoint in JSON mode. temperature
    is always passed explicitly, never left to inherit a library/provider
    default (P1 Day 23 finding, see CLAUDE.md)."""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=False,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if content is None:
        raise ValueError("DeepSeek response had no content (message.content was None)")

    usage = response.usage
    if usage is None:
        raise ValueError("DeepSeek response had no usage data")

    return CallResult(
        text=content,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        stop_reason=response.choices[0].finish_reason,
        model_name=response.model,
    )
