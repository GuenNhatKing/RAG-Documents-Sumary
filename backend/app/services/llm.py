import os
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.env import load_backend_env

load_backend_env()

_client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)


def _get_extra_body() -> dict | None:
    """Trả về extra_body để bật/tắt chế độ suy nghĩ của mô hình tùy thuộc vào LLM_THINK."""
    llm_think = os.getenv("LLM_THINK", "true").lower()
    if llm_think == "false":
        return {"think": False}
    return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
)
def generate_final_answer(context: str, query: str) -> str:
    """LLM Generation Service: generate Markdown answer from retrieved context."""
    if not context.strip():
        return "**Tài liệu không đề cập đến vấn đề này.**"

    model_name = os.getenv("LLM_MODEL")
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    system_prompt = """Bạn là một trợ lý AI phân tích tài liệu chuyên nghiệp.

Quy tắc bắt buộc:
1. CHỈ trả lời dựa trên ngữ cảnh (context) được cung cấp. Không tự ý sử dụng kiến thức bên ngoài tài liệu.
2. Nếu ngữ cảnh không có thông tin hoặc không đủ để trả lời câu hỏi, bạn BẮT BUỘC phải trả lời chính xác câu sau: **Tài liệu không đề cập đến vấn đề này.**
3. Trình bày câu trả lời bằng định dạng Markdown (tiêu đề ngắn, danh sách gạch đầu dòng, bảng nếu phù hợp).
4. Sử dụng chữ **in đậm** cho các thuật ngữ hoặc con số quan trọng.
5. Tuyệt đối không tự bịa đặt, suy diễn, hoặc biến đổi vai trò của tài liệu (ví dụ: không được biến thông tin cá nhân trong CV thành quy định yêu cầu của trường học).
6. Trả lời bằng tiếng Việt, ngắn gọn và chính xác."""

    context = _truncate_context(context)

    extra_body = _get_extra_body()
    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context + "\n\nQuestion: " + query},
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

    model_name = os.getenv("LLM_MODEL")
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

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
    model_name = os.getenv("LLM_MODEL")
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    system_prompt = """You are a helpful, professional Vietnamese document analysis AI assistant.
Respond to the user's greeting, small talk, or conversational message in a polite, friendly, and helpful way in Vietnamese.
Remind them gently that you are here to assist with document analysis or answering questions based on the uploaded documents.
Be concise (1-2 sentences). Do not include any sources or references."""

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
