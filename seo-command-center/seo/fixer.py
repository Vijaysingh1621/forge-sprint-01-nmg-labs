"""
fixer.py — local LLM-driven fix generation for SEO issues.
Uses a local Ollama instance to rewrite titles and meta descriptions.
"""
from __future__ import annotations
import requests
import json
import csv
import os

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:31b-cloud" # Updated to use requested model

def get_llm_completion(prompt: str) -> str:
    """Simple wrapper for local Ollama API."""
    try:
        payload = {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 200, "temperature": 0.3}
        }
        response = requests.post(OLLAMA_URL, json=payload, timeout=1)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        return f"Error calling LLM: {str(e)}"

def generate_title(url: str, current_title: str, content_sample: str = "") -> str:
    """Generate an SEO-optimized title (< 60 chars)."""
    prompt = (
        f"Task: Rewrite the following SEO page title to be more engaging and keyword-rich.\n"
        f"URL: {url}\n"
        f"Current Title: {current_title}\n"
        f"Constraint: Maximum 60 characters.\n"
        f"Output only the new title text, no commentary."
    )
    return get_llm_completion(prompt)

def generate_meta(url: str, current_meta: str, current_title: str) -> str:
    """Generate an SEO-optimized meta description (< 155 chars)."""
    prompt = (
        f"Task: Create a compelling meta description for this page.\n"
        f"URL: {url}\n"
        f"Title: {current_title}\n"
        f"Current Meta: {current_meta}\n"
        f"Constraint: Maximum 155 characters.\n"
        f"Output only the meta description text, no commentary."
    )
    return get_llm_completion(prompt)

def suggest_redirect(broken_url: str, all_urls: list[str]) -> str:
    """Suggest the best possible redirect target for a 4xx broken link."""
    # In a real scenario, we'd use a vector DB or fuzzy matching.
    # For the sprint, we'll use the LLM to pick the most likely match from the list.
    candidates = all_urls[:50] # Limit candidates to avoid context overflow
    prompt = (
        f"Task: Find the best redirect target for a broken URL from a list of valid URLs.\n"
        f"Broken URL: {broken_url}\n"
        f"Candidates:\n" + "\n".join(candidates) + "\n"
        f"Constraint: Output only the target URL. If no good match, output 'NONE'."
    )
    return get_llm_completion(prompt)
