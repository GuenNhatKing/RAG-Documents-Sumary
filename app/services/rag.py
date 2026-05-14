import json
import os
from typing import List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

# OpenRouter client singleton
_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)


def _normalize_tree_node(node_data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively copy a tree node, keeping only the fields needed for searching."""
    normalized = {
        "id": node_data["id"],
        "title": node_data["title"],
        "summary": node_data.get("summary", ""),
    }
    # Preserve children if present
    if "children" in node_data:
        normalized["children"] = _normalize_tree_node(node_data["children"])
    elif "nodes" in node_data:  # alternative field name
        normalized["children"] = _normalize_tree_node(node_data["nodes"])
    return normalized


def _build_search_prompt(tree_without_text: Dict[str, Any], query: str) -> str:
    """Create the prompt used to query the LLM."""
    search_prompt = f"""
You are an expert document navigator. You are given a question and a tree structure of a document's table of contents.
Each node contains an id, title, and a corresponding summary.
Your task is to find all nodes that are likely to contain the exact answer to the question.

Question: {query}

Document tree structure:
{json.dumps(tree_without_text, indent=2, ensure_ascii=False)}

Please reply EXACTLY in the following JSON format. Do not output any markdown code blocks, just the raw JSON:
{{
    "thinking": "<Your step-by-step reasoning on why these nodes are relevant>",
    "node_list": ["id_1", "id_2"]
}}
"""
    return search_prompt


def reasoning_search_tree(
    tree_data: Dict[str, Any], query: str
) -> List[str]:
    # Existing function body remains unchanged
    """
    Given a document tree and a user query, find the most relevant node IDs.
    The function:
      1. Normalizes the tree to keep only id, title, and summary fields.
      2. Sends the normalized tree to a LLM via OpenRouter.
      3. Parses the JSON response and returns the list of node IDs.
    Args:
        tree_data: The full tree structure (may be large) returned by pageindex_service.
        query:   The user's question/search term.
    Returns:
        A list of node IDs (strings) that are most relevant to the query.
    """
    # 1️⃣ Normalize the incoming tree – keep hierarchy, drop heavy text fields
    normalized_tree = _normalize_tree_node(tree_data)

    # 2️⃣ Build the prompt
    prompt = _build_search_prompt(normalized_tree, query)

    # 3️⃣ Call OpenRouter
    try:
        response = _client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.0,
        )
    except Exception as e:
        # In production you might want richer error handling
        raise RuntimeError(f"Failed to call OpenRouter: {e}")

    raw_output = response.choices[0].message.content.strip()

    # 4️⃣ Clean potential markdown fences and parse JSON
    # Remove accidental ```json or ```python fences
    cleaned = raw_output.replace("```json", "").replace("```", "").replace("```python", "")
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Unable to parse LLM output as JSON: {cleaned}") from exc

    return parsed.get("node_list", [])