from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str


@dataclass(frozen=True)
class LLMCallResult:
    response: LLMResponse | None
    failure_type: str | None = None
    failure_message: str | None = None


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
        result = self.chat_with_diagnostics(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            enable_thinking=enable_thinking,
        )
        return result.response

    def chat_with_diagnostics(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        model: str | None = None,
        enable_thinking: bool | None = None,
    ) -> LLMCallResult:
        if not self.is_available():
            return LLMCallResult(response=None, failure_type="not_configured", failure_message="LLM 未配置可用的 API Key 或模型名。")
        if self.client is None:
            return LLMCallResult(response=None, failure_type="client_unavailable", failure_message="LLM 客户端未初始化。")

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
        except Exception as error:
            return LLMCallResult(
                response=None,
                failure_type="request_error",
                failure_message=f"LLM 调用失败: {error}",
            )

        choices = getattr(response, "choices", None) or []
        if not choices:
            return LLMCallResult(response=None, failure_type="empty_choices", failure_message="LLM 返回为空 choices。")
        message = getattr(choices[0], "message", None)

        finish = getattr(choices[0], "finish_reason", None) or "unknown"

        content = self._normalize_message_content(getattr(message, "content", None))
        if not content:
            # DeepSeek reasoner / thinking models may put output in reasoning_content
            reasoning = getattr(message, "reasoning_content", None)
            content = self._normalize_message_content(reasoning)
        if not content:
            return LLMCallResult(
                response=None,
                failure_type="empty_content",
                failure_message=f"LLM 返回响应但 content 为空（finish_reason={finish}）。模型可能在思考阶段未产出最终答案，可尝试调大 max_tokens 或重试。",
            )

        response_model = getattr(response, "model", None) or request_model
        return LLMCallResult(response=LLMResponse(content=content, model=str(response_model)))

    def chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_base64: str,
        image_type: str = "image/png",
        temperature: float = 0.1,
        max_tokens: int = 1600,
        model: str | None = None,
    ) -> str | None:
        if not self.is_available() or self.client is None:
            return None

        request_model = (model or self.model).strip()
        data_url = f"data:{image_type};base64,{image_base64}"

        try:
            response = self.client.chat.completions.create(
                model=request_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ]},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body={"enable_thinking": False} if "dashscope.aliyuncs.com" in self.base_url else None,
            )
        except Exception:
            return None

        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        message = getattr(choices[0], "message", None)
        content = self._normalize_message_content(getattr(message, "content", None))
        if not content:
            reasoning = getattr(message, "reasoning_content", None)
            content = self._normalize_message_content(reasoning)
        return content or None

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