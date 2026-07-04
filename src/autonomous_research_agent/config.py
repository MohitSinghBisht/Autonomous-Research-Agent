from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    openai_api_key: str
    tavily_api_key: str
    light_model: str = "gpt-4.1-mini"
    mid_model: str = "gpt-4.1-mini"
    heavy_model: str = "gpt-4.1"
    max_attempts: int = 4

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing. Add it to your environment or .env file.")

        tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
        if not tavily_key:
            raise ValueError("TAVILY_API_KEY is missing. Add it to your environment or .env file.")

        return cls(
            openai_api_key=api_key,
            tavily_api_key=tavily_key,
            light_model=os.getenv("OPENAI_LIGHT_MODEL", "gpt-5.4-mini").strip() or "gpt-4.1-mini",
            mid_model=os.getenv("OPENAI_MID_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            heavy_model=os.getenv("OPENAI_HEAVY_MODEL", "gpt-4.1").strip() or "gpt-4.1",
            max_attempts=int(os.getenv("MAX_ATTEMPTS", "4")),
        )
