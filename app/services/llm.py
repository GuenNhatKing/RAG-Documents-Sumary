import os
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

# Task 3.3: Tự động gọi lại nếu OpenRouter nghẽn (429) hoặc sập (503)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
def generate_final_answer(context: str, query: str) -> str:
    """Task 3.1: LLM Generation Service."""
    if not context.strip():
        return "Tài liệu không đề cập đến vấn đề này."

    model_name = os.getenv("OPENROUTER_MODEL")

    system_prompt = """You are a professional document analysis AI assistant.
    ULTIMATE AND UNBREAKABLE RULES:
    1. STRICT CONTEXT ADHERENCE: You must formulate your answer SOLELY, EXCLUSIVELY, and DIRECTLY based on the provided "Context" below. Do not use any external knowledge, pre-trained information, assumptions, speculations, or multi-step logical leaps. If a fact is not explicitly written in the Context, it does not exist for you.
    2. ZERO-HALLUCINATION FALLBACK: If the Context does not contain the exact, definitive answer to the question, or if the information is insufficient to provide a complete answer, you MUST reply with this exact phrase and absolutely nothing else: "Tài liệu không đề cập đến vấn đề này". Do not add any apologies, introductions, or further explanations.
    3. MANDATORY IN-LINE CITATIONS: Every single claim, fact, or idea in your response must be strictly cited at the immediate end of that specific sentence or point. The citation must strictly match and use the formatting tags found within the Context, specifically `[Nguồn: ..., Dòng: ...]`. (Example: ...theo quy định [Dòng 22-23]). Never invent, guess, or modify the source file name or line numbers.
    """

    user_prompt = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"

    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.0,
        max_tokens=2000
    )

    return response.choices[0].message.content.strip()
