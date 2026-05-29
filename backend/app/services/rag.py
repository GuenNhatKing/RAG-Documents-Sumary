import json
import os
import re
from typing import List, Dict, Any
from openai import OpenAI
from app.env import load_backend_env
from tenacity import retry, stop_after_attempt, wait_fixed, wait_exponential, retry_if_exception_type

load_backend_env()

# Read LLM configuration from environment
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL")
_client = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
)


def _normalize_tree_node(node_data: Dict[str, Any]) -> Dict[str, Any]:
    """Chuẩn hóa cây để gửi cho LLM, giữ cấu trúc cha-con."""
    normalized = {
        "id": str(node_data.get("node_id", node_data.get("id"))),
        "title": node_data.get("title", ""),
        "summary": node_data.get("summary", node_data.get("prefix_summary", "")),
    }

    if "children" in node_data:
        normalized["children"] = [
            _normalize_tree_node(child)
            for child in node_data["children"]
        ]
    elif "nodes" in node_data:
        normalized["children"] = [
            _normalize_tree_node(child)
            for child in node_data["nodes"]
        ]

    return normalized


def _get_all_line_numbers(node: Dict[str, Any], line_nums: List[int]):
    """Helper để lấy tất cả line_num, hỗ trợ cả key 'structure' bọc ngoài."""
    ln = node.get("line_num")

    if ln is not None:
        line_nums.append(int(ln))

    for child_key in ("structure", "children", "nodes"):
        if child_key in node:
            for child in node[child_key]:
                _get_all_line_numbers(child, line_nums)


def _find_node_and_boundary(tree_data: Any, target_id: str) -> Dict[str, Any]:
    """Tìm node theo ID và xác định chính xác dòng bắt đầu/kết thúc."""
    all_lines = []

    if isinstance(tree_data, list):
        for n in tree_data:
            _get_all_line_numbers(n, all_lines)
    else:
        _get_all_line_numbers(tree_data, all_lines)

    all_lines = sorted(list(set(all_lines)))

    def _search(node: Dict[str, Any], tid: str):
        curr_id = str(node.get("node_id") or node.get("id"))

        if curr_id == tid:
            start = node.get("line_num")
            end = None

            if start is not None:
                try:
                    idx = all_lines.index(int(start))
                    if idx + 1 < len(all_lines):
                        end = all_lines[idx + 1] - 1
                except ValueError:
                    pass

            return {
                "start": start,
                "end": end,
            }

        for child_key in ("structure", "children", "nodes"):
            if child_key in node:
                for child in node[child_key]:
                    res = _search(child, tid)
                    if res:
                        return res

        return None

    nodes_to_check = tree_data if isinstance(tree_data, list) else [tree_data]

    for root_node in nodes_to_check:
        result = _search(root_node, target_id)
        if result:
            return result

    return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_reasoning_llm(prompt: str) -> Dict[str, Any]:
    """Gọi LLM để tìm node liên quan, có retry bằng tenacity."""
    response = _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a document analysis AI. Answer precisely and concisely. Return only JSON, no explanation.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=1500,
        temperature=0.0,
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("LLM trả về nội dung rỗng")

    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    result = json.loads(cleaned)

    if not isinstance(result, dict):
        raise ValueError("JSON trả về không phải object")

    node_list = result.get("node_list")

    if node_list is None:
        raise ValueError("JSON trả về thiếu key node_list")

    if not isinstance(node_list, list):
        raise ValueError("node_list không phải list")

    return result


def _tree_to_text_outline(nodes: List[Dict[str, Any]], indent_level: int = 0) -> str:
    """Chuyển đổi cây đã được chuẩn hóa thành dạng outline thụt lề bằng văn bản gọn nhẹ."""
    lines = []
    indent = "  " * indent_level
    for node in nodes:
        node_id = node.get("id")
        title = node.get("title", "")
        summary = node.get("summary", "")
        
        line = f"{indent}- [{node_id}] {title}"
        if summary:
            # Rút gọn khoảng trắng thừa trong tóm tắt để giảm kích thước token
            clean_summary = " ".join(summary.split())
            line += f": {clean_summary}"
          
        lines.append(line)
        
        if "children" in node and node["children"]:
            lines.append(_tree_to_text_outline(node["children"], indent_level + 1))
            
    return "\n".join(lines)


def reasoning_search_tree(tree_data: Any, query: str) -> List[str]:
    """Task 2.1: Duyệt cây bằng Reasoning."""
    if isinstance(tree_data, dict) and "structure" in tree_data:
        base_data = tree_data["structure"]
    else:
        base_data = tree_data

    normalized_tree = {
        "nodes": [
            _normalize_tree_node(n)
            for n in (base_data if isinstance(base_data, list) else [base_data])
        ]
    }

    prompt = f"""You are a document navigation expert. Find the IDs of the nodes that are most likely to contain the answer to the user's question.

Question: {query}

Tree structure outline:
{_tree_to_text_outline(normalized_tree["nodes"])}

Return only a JSON object with the "node_list" key containing the list of relevant node IDs.
Example: {{"node_list": ["id_1", "id_2"]}}
Do not include any explanations, thinking process, or other keys. Keep the response as short as possible."""

    try:
        result = _call_reasoning_llm(prompt)
        return [str(node_id) for node_id in result.get("node_list", [])]

    except Exception as e:
        print(f"Error in reasoning_search_tree: {e}")
        return []


def build_context_from_markdown(tree_data: Any, node_list: List[str], markdown_path: str, display_name: str = "") -> str:
    """Task 2.2: Trích xuất nội dung theo dòng từ file .md duy nhất."""
    if not os.path.exists(markdown_path):
        return f"⚠️ Không tìm thấy file markdown tại: {markdown_path}"

    with open(markdown_path, "r", encoding="utf-8") as f:
        all_lines = f.readlines()

    context_parts = []
    processed_ranges = []

    for nid in node_list:
        boundary = _find_node_and_boundary(tree_data, nid)

        if not boundary or boundary["start"] is None:
            continue

        start_idx = int(boundary["start"]) - 1

        end_idx = int(boundary["end"]) if boundary["end"] else start_idx + 20

        end_idx = min(end_idx, len(all_lines))

        segment = all_lines[start_idx:end_idx]

        if segment:
            source_file = display_name if display_name else os.path.basename(markdown_path)
            source_tag = (
                f"[Nguồn: {source_file}, "
                f"Dòng: {boundary['start']}-{boundary['end'] or '...'}]"
            )
            context_parts.append(f"{source_tag}\n{''.join(segment).strip()}")

    return "\n\n---\n\n".join(context_parts)
