import os
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
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

    model_name = os.getenv("OPENROUTER_MODEL")

    system_prompt = """You are a professional document analysis AI assistant.

ULTIMATE AND UNBREAKABLE RULES:

1. STRICT CONTEXT ADHERENCE:
You must answer SOLELY, EXCLUSIVELY, and DIRECTLY based on the provided Context.
Do not use external knowledge, assumptions, speculation, or unstated facts.
If a fact is not explicitly present in the Context, it does not exist for you.

2. ZERO-HALLUCINATION FALLBACK:
If the Context does not contain enough information to answer the question, reply exactly:
**Tài liệu không đề cập đến vấn đề này.**

3. MARKDOWN OUTPUT:
Your answer must be valid Markdown.
Use:
- short headings when useful
- bullet lists for enumerations
- numbered lists for ordered steps
- Markdown tables when comparing multiple fields
- **bold** for important terms or conclusions

4. NO RAW SOURCE TAGS IN FINAL TEXT:
The Context may contain source tags like:
[Nguồn: ..., Dòng: ...]

You MUST use those tags only internally to verify evidence.
Do NOT include source tags in the final answer text.
Do NOT write citations like [Nguồn: ..., Dòng: ...].
Do NOT write line numbers in the final answer.

5. ANSWER STYLE:
- Answer in Vietnamese.
- Be concise but complete.
- Do not add introductions like "Dựa trên tài liệu...".
- Do not wrap the whole answer in a code block.
- Do not output HTML.
"""

    user_prompt = f"""Context:
{context}

Question:
{query}

Answer in Markdown:
"""

    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.0,
        max_tokens=2000,
    )

    content = response.choices[0].message.content

    if not content:
        return "**Tài liệu không đề cập đến vấn đề này.**"

    return content.strip()