import os
import re
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.env import load_backend_env

load_backend_env()

_client = OpenAI(
    api_key=os.getenv("RAG_API_KEY") or os.getenv("LLM_API_KEY"),
    base_url=os.getenv("RAG_BASE_URL") or os.getenv("LLM_BASE_URL"),
)

_MODEL_NAME = os.getenv("RAG_MODEL") or os.getenv("LLM_MODEL")


def _get_extra_body() -> dict | None:
    """Trả về extra_body để bật/tắt chế độ suy nghĩ của mô hình tùy thuộc vào LLM_THINK."""
    rag_base_url = os.getenv("RAG_BASE_URL")
    if rag_base_url and "groq.com" in rag_base_url:
        return None
    llm_think = os.getenv("LLM_THINK", "true").lower()
    if llm_think == "false":
        return {"think": False}
    return None


def _is_groq() -> bool:
    rag_base_url = os.getenv("RAG_BASE_URL") or os.getenv("LLM_BASE_URL")
    return bool(rag_base_url and "groq.com" in rag_base_url)


def _get_groq_capped_max_tokens(prompt_text: str, default_max: int, limit: int = 5800) -> int:
    """Cap max_tokens for Groq to avoid exceeding the TPM limit (e.g. 6000)."""
    if not _is_groq():
        return default_max
    
    # Estimate tokens in the prompt. We assume 1 character is roughly 0.4 tokens (conservative estimate).
    # Plus a small buffer of 50 tokens.
    estimated_prompt_tokens = int(len(prompt_text) * 0.4) + 50
    
    # Calculate remaining tokens under the limit
    remaining = limit - estimated_prompt_tokens
    
    # Ensure remaining is at least 256 tokens so the model can actually respond
    capped = max(256, remaining)
    
    # Cap to the default_max requested by the caller
    return min(capped, default_max)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
)
def generate_final_answer(context: str, query: str) -> str:
    """LLM Generation Service: generate Markdown answer from retrieved context."""
    if not context.strip():
        return "**Tài liệu không đề cập đến vấn đề này.**"

    model_name = _MODEL_NAME
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    system_prompt = """Bạn là một trợ lý AI phân tích tài liệu chuyên nghiệp.

Quy tắc bắt buộc:
1. CHỈ trả lời dựa trên ngữ cảnh (context) được cung cấp. Không tự ý sử dụng kiến thức bên ngoài tài liệu.
2. Kiểm tra kỹ xem ngữ cảnh có chứa thông tin để trả lời cho câu hỏi hay không:
   - Nếu CÓ thông tin: Trả lời câu hỏi một cách ngắn gọn, chính xác dựa trên ngữ cảnh. Tuyệt đối KHÔNG viết thêm câu "Tài liệu không đề cập đến vấn đề này." vào bất kỳ vị trí nào trong câu trả lời.
   - Nếu KHÔNG có thông tin hoặc không đủ thông tin: Chỉ trả lời duy nhất câu sau, không viết thêm bất kỳ từ nào khác: **Tài liệu không đề cập đến vấn đề này.**
3. Trình bày câu trả lời bằng định dạng Markdown (tiêu đề ngắn, danh sách gạch đầu dòng, bảng nếu phù hợp).
4. Sử dụng chữ **in đậm** cho các thuật ngữ hoặc con số quan trọng.
5. Tuyệt đối không tự bịa đặt, suy diễn, hoặc biến đổi vai trò của tài liệu (ví dụ: không được biến thông tin cá nhân trong CV thành quy định yêu cầu của trường học).
6. Trả lời bằng tiếng Việt, ngắn gọn và chính xác.
7. Ở cuối câu trả lời, nếu có thông tin, bạn BẮT BUỘC phải trích dẫn chính xác thẻ nguồn dạng [Nguồn: tên_file, Dòng: start-end] tương ứng với đoạn chứa thông tin trả lời trong ngữ cảnh. Không tự ý thay đổi tên file hay số dòng."""

    context = _truncate_context(context)
    user_content = f"Dưới đây là ngữ cảnh trích xuất từ tài liệu:\n{context}\n\nHãy trả lời câu hỏi sau:\nQuestion: {query}"
    prompt_text = system_prompt + user_content
    max_tokens = _get_groq_capped_max_tokens(prompt_text, max_tokens)

    extra_body = _get_extra_body()
    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
        extra_body=extra_body if extra_body else None,
    )

    content = response.choices[0].message.content

    if not content:
        return "**Tài liệu không đề cập đến vấn đề này.**"

    return content.strip()


_SUMMARY_LENGTH_INSTRUCTIONS = {
    "short": "Summarize BRIEFLY, only state the most important points in 3-5 sentences.",
    "medium": "Summarize all main points, 1-2 sentences per point.",
    "long": "Summarize in detail, covering all important points and illustrative examples.",
}


def _truncate_context(context: str, max_chars: int = 6000) -> str:
    """Truncate context to fit model's context window, keeping start and end."""
    if len(context) <= max_chars:
        return context
    half = max_chars // 2
    return context[:half] + "\n\n...[TRUNCATED]...\n\n" + context[-half:]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
)
def generate_summary(context: str, length: str = "medium") -> str:
    """Generate a structured summary of the document context.

    Args:
        context: Full document text to summarize.
        length: One of "short", "medium", "long".

    Returns:
        Markdown-formatted summary.
    """
    if not context.strip():
        return "**Không có nội dung để tóm tắt.**"

    length_instruction = _SUMMARY_LENGTH_INSTRUCTIONS.get(length, _SUMMARY_LENGTH_INSTRUCTIONS["medium"])

    model_name = _MODEL_NAME
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    # Adjust default max_tokens for summary lengths to be more optimal
    if length == "short":
        max_tokens = min(max_tokens, 512)
    elif length == "medium":
        max_tokens = min(max_tokens, 1024)
    else:
        max_tokens = min(max_tokens, 1500)

    system_prompt = """You are a Vietnamese administrative document summarization assistant.

Rules:
1. Use ONLY information from the provided text. Do not add external information.
2. Respond in well-structured Markdown (headings, bullet points).
3. Use **bold** for important terms.
4. Do not include code blocks.
5. Respond in Vietnamese."""

    context = _truncate_context(context)

    user_prompt = f"""Summarize the following document.

{length_instruction}

Document:
{context}"""

    prompt_text = system_prompt + user_prompt
    max_tokens = _get_groq_capped_max_tokens(prompt_text, max_tokens)

    extra_body = _get_extra_body()
    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
        extra_body=extra_body if extra_body else None,
    )

    content = response.choices[0].message.content

    if not content:
        return "**Không thể tạo tóm tắt. Vui lòng thử lại.**"

    return content.strip()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
)
def generate_conversational_response(query: str) -> str:
    """Generate a friendly response for general greetings or small talk."""
    model_name = _MODEL_NAME
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    max_tokens = min(max_tokens, 512)

    system_prompt = """You are a helpful, professional Vietnamese document analysis AI assistant.
Respond to the user's greeting, small talk, or conversational message in a polite, friendly, and helpful way in Vietnamese.
Remind them gently that you are here to assist with document analysis or answering questions based on the uploaded documents.
Be concise (1-2 sentences). Do not include any sources or references."""

    prompt_text = system_prompt + query
    max_tokens = _get_groq_capped_max_tokens(prompt_text, max_tokens)

    extra_body = _get_extra_body()
    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.7,
        max_tokens=max_tokens,
        extra_body=extra_body if extra_body else None,
    )

    content = response.choices[0].message.content
    return content.strip() if content else "Xin chào! Tôi có thể giúp gì cho bạn về tài liệu này?"


def condense_query(query: str, history: list) -> str:
    """Rewrite follow-up query based on chat history to make it standalone for RAG."""
    if not history:
        return query

    # Format history (last 5 messages)
    history_str = ""
    for msg in history[-5:]:
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
        role_label = "User" if role == "user" else "Assistant"
        history_str += f"{role_label}: {content}\n"

    prompt = f"""Given the following chat history and a follow-up question, rewrite the follow-up question to be a standalone search query that contains all necessary context from the conversation history.

CHAT HISTORY:
{history_str}

FOLLOW-UP QUESTION: {query}

Standalone search query (in Vietnamese, be concise, return ONLY the query text, no explanation or code blocks):"""

    try:
        extra_body = _get_extra_body()
        response = _client.chat.completions.create(
            model=_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.0,
            extra_body=extra_body if extra_body else None,
        )
        content = response.choices[0].message.content
        if content:
            cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
            return cleaned.strip()
    except Exception as e:
        print(f"Error in condense_query: {e}", flush=True)

    return query
