from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str


@dataclass(frozen=True)
class LLMProfile:
    model: str
    temperature: float = 0.1
    max_tokens: int = 1200
    enable_thinking: bool = False


class OpenAICompatibleLLM:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 45,
        enable_thinking: bool = False,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.enable_thinking = enable_thinking
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout_seconds) if self.api_key else None

    def is_available(self) -> bool:
        return bool(self.api_key and self.model)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        model: str | None = None,
        enable_thinking: bool | None = None,
    ) -> LLMResponse | None:
        if not self.is_available():
            return None
        if self.client is None:
            return None

        request_model = (model or self.model).strip()
        request_thinking = self.enable_thinking if enable_thinking is None else enable_thinking

        extra_body = {"enable_thinking": True} if request_thinking and "dashscope.aliyuncs.com" in self.base_url else None

        try:
            response = self.client.chat.completions.create(
                model=request_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body,
            )
        except Exception:
            return None

        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        message = getattr(choices[0], "message", None)
        content = self._normalize_message_content(getattr(message, "content", None))
        if not content:
            return None

        response_model = getattr(response, "model", None) or request_model
        return LLMResponse(content=content, model=str(response_model))

    def _normalize_message_content(self, content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text_value = item.get("text") or item.get("content")
                    if text_value:
                        text_parts.append(str(text_value))
            return "\n".join(text_parts).strip()
        return str(content or "").strip()