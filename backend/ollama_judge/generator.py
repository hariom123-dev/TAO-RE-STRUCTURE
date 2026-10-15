"""
Generator — Calls Ollama to produce the initial LLM response.

This is the "Prover" in TAO terminology — it produces the response
that gets scrutinized by the Judge.
"""

import json
import time
from typing import Optional

import httpx

from backend.ollama_judge.config import ollama_config


DEFAULT_SYSTEM_PROMPT = """You are a helpful, accurate, and honest AI assistant.

Rules you MUST follow:
1. Be factually accurate — do NOT make up information
2. If you're unsure, say so explicitly
3. Do NOT blindly agree with the user if they're wrong
4. Provide balanced, evidence-based responses
5. For medical/legal/financial questions, recommend professional consultation
6. Never produce harmful, illegal, or dangerous content"""


async def generate(
    user_message: str,
    system_prompt: str = "",
    model: Optional[str] = None,
    temperature: Optional[float] = None, 
) -> tuple[str, int, float]:
    """
    Generate a response from the Ollama LLM.

    Args:
        user_message: The user's input
        system_prompt: Optional custom system prompt
        model: Override model (default: config.generator_model)
        temperature: Override temperature

    Returns:
        tuple of (response_text, tokens_used, latency_ms)
    """
    model = model or ollama_config.generator_model
    temp = temperature if temperature is not None else ollama_config.generator_temperature
    system = system_prompt or DEFAULT_SYSTEM_PROMPT

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": temp,
            "num_predict": ollama_config.generator_max_tokens,
        },
    }

    start = time.time()

    async with httpx.AsyncClient(timeout=ollama_config.request_timeout) as client:
        resp = await client.post(
            f"{ollama_config.ollama_base_url}/api/chat",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    latency_ms = round((time.time() - start) * 1000, 1)

    response_text = data.get("message", {}).get("content", "")
    tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

    return response_text, tokens, latency_ms
