import json
import os
from typing import List, Dict, Any, Set, Union
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

def _normalize_tree_node(node_data: Dict[str, Any]) -> Dict[str, Any]:
    """Chuẩn hóa cây để gửi cho LLM, giữ cấu trúc cha-con."""
    normalized = {
        "id": str(node_data.get("node_id", node_data.get("id"))),
        "title": node_data.get("title", ""),
        "summary": node_data.get("summary", node_data.get("prefix_summary", "")),
    }
    if "children" in node_data:
        normalized["children"] = [_normalize_tree_node(child) for child in node_data["children"]]
    elif "nodes" in node_data:
        normalized["children"] = [_normalize_tree_node(child) for child in node_data["nodes"]]
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
        for n in tree_data: _get_all_line_numbers(n, all_lines)
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
            return {"start": start, "end": end}
            
        for child_key in ("structure", "children", "nodes"):
            if child_key in node:
                for child in node[child_key]:
                    res = _search(child, tid)
                    if res: return res
        return None

    nodes_to_check = tree_data if isinstance(tree_data, list) else [tree_data]
    for root_node in nodes_to_check:
        result = _search(root_node, target_id)
        if result: return result
    return None

def reasoning_search_tree(tree_data: Any, query: str) -> List[str]:
    """Task 2.1: Duyệt cây bằng Reasoning."""
    if isinstance(tree_data, dict) and "structure" in tree_data:
        base_data = tree_data["structure"]
    else:
        base_data = tree_data

    normalized_tree = {"nodes": [_normalize_tree_node(n) for n in (base_data if isinstance(base_data, list) else [base_data])]}
    
    prompt = f"""You are an expert document navigator. Find nodes likely to contain the answer.
Question: {query}
Tree Structure:
{json.dumps(normalized_tree, indent=2, ensure_ascii=False)}

Reply EXACTLY in JSON:
{{
    "thinking": "<reasoning>",
    "node_list": ["id_1", "id_2"]
}}"""

    try:
        response = _client.chat.completions.create(
            model="openrouter/free",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.0,
        )
        cleaned = response.choices[0].message.content.strip().replace("```json", "").replace("```", "")
        return json.loads(cleaned).get("node_list", [])
    except Exception as e:
        print(f"Error in reasoning_search_tree: {e}")
        return []

def build_context_from_markdown(tree_data: Any, node_list: List[str], markdown_path: str) -> str:
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
        # Nếu không tìm thấy node kế tiếp, lấy 20 dòng làm context mặc định
        end_idx = int(boundary["end"]) if boundary["end"] else start_idx + 20
        
        # Đảm bảo không vượt quá số dòng thực tế
        end_idx = min(end_idx, len(all_lines))
        
        # Trích xuất và format
        segment = all_lines[start_idx:end_idx]
        if segment:
            source_tag = f"[Nguồn: {os.path.basename(markdown_path)}, Dòng: {boundary['start']}-{boundary['end'] or '...'}]"
            context_parts.append(f"{source_tag}\n{''.join(segment).strip()}")

    return "\n\n---\n\n".join(context_parts)