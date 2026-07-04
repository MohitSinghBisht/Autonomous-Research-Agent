from __future__ import annotations

from typing import TypeVar

from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import BaseModel

from .config import Settings


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class OpenAIReasoner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = wrap_openai(OpenAI(api_key=settings.openai_api_key))

    def parse_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        use_web_search: bool = False,
    ) -> SchemaT:
        request_kwargs = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "text_format": schema,
        }

        if use_web_search:
            request_kwargs["tools"] = [{"type": "web_search_preview"}]

        response = self.client.responses.parse(**request_kwargs)
        return response.output_parsed
