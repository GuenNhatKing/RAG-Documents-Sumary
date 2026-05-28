import os
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.env import load_backend_env

load_backend_env()

_client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)


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
    num_ctx = int(os.getenv("LLM_NUM_CTX", "8192"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    think = os.getenv("LLM_THINK", "false").lower() == "true"
    keep_alive = os.getenv("LLM_KEEP_ALIVE", "10m")

    system_prompt = """You are a professional document analysis AI assistant.

Mandatory rules:
1. Answer ONLY based on the provided context. Do not use external knowledge.
2. If the context is insufficient, reply: **Tài liệu không đề cập đến vấn đề này.**
3. Answer in Markdown: short headings, bullet lists, tables when appropriate.
4. Use **bold** for important terms.
5. Do not include source tags in the answer.
6. Do not wrap the entire answer in a code block.
7. Answer in Vietnamese, concise but complete."""

    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context + "\n\nQuestion: " + query},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
        extra_body={
            "think": think,
            "keep_alive": keep_alive,
            "options": {"num_ctx": num_ctx, "temperature": 0, "top_p": 0.9, "top_k": 20},
        },
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
    num_ctx = int(os.getenv("LLM_NUM_CTX", "8192"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    think = os.getenv("LLM_THINK", "false").lower() == "true"
    keep_alive = os.getenv("LLM_KEEP_ALIVE", "10m")

    system_prompt = """You are a Vietnamese administrative document summarization assistant.

Rules:
1. Use ONLY information from the provided text. Do not add external information.
2. Respond in well-structured Markdown (headings, bullet points).
3. Use **bold** for important terms.
4. Do not include code blocks.
5. Respond in Vietnamese."""

    user_prompt = f"""Summarize the following document.

{length_instruction}

Document:
{context}"""

    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
        extra_body={
            "think": think,
            "keep_alive": keep_alive,
            "options": {"num_ctx": num_ctx, "temperature": 0, "top_p": 0.9, "top_k": 20},
        },
    )

    content = response.choices[0].message.content

    if not content:
        return "**Không thể tạo tóm tắt. Vui lòng thử lại.**"

    return content.strip()
