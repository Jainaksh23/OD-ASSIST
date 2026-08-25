"""
eval/run_evaluation.py — Custom LLM-as-a-Judge RAG Evaluation Harness.

Uses Groq (qwen/qwen3.6-27b) to evaluate:
  - Faithfulness: Is the answer grounded in the retrieved context?
  - Answer Relevancy: Does the answer address the question asked?
  - Precision@3: Are the expected sources in the top-3 retrieved?

Outputs results to eval/eval_results.json with per-question breakdown.
"""

import json
import os
import re
import sys
import requests
import time
from langchain_groq import ChatGroq
from dotenv import load_dotenv

# Add project root to path so we can import db modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

API_URL = "http://127.0.0.1:7860/chat/query"

# LLM judge
llm = ChatGroq(model_name="qwen/qwen3.6-27b", temperature=0)


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks from reasoning-capable model output."""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def extract_score(res: str) -> float:
    """Extract a 0 or 1 score from LLM judge output, handling thinking tags."""
    cleaned = strip_thinking(res)
    match = re.search(r'(0|1)', cleaned)
    if match:
        return float(match.group(1))
    return 0.0


def get_chunk_texts_for_sources(source_ids: list) -> str:
    """Fetch actual chunk text from DB for the given source IDs."""
    from db.db import SessionLocal
    from db.models import Chunk
    db = SessionLocal()
    try:
        chunks = db.query(Chunk.chunk_text).filter(
            Chunk.source_id.in_(source_ids)
        ).limit(10).all()
        return "\n---\n".join([c.chunk_text[:500] for c in chunks if c.chunk_text])
    finally:
        db.close()


def evaluate_faithfulness(question: str, answer: str, context: str) -> float:
    """Judge whether the answer is grounded in the retrieved context."""
    prompt = f"""You are an evaluation judge. Given a QUESTION, CONTEXT (retrieved documents), and ANSWER, determine if the ANSWER is faithful to the CONTEXT.

Rules:
- If the answer's claims can be directly inferred from the context, output ONLY the number: 1
- If the answer makes claims NOT supported by the context, output ONLY the number: 0
- If the answer says "I don't know" or similar, and the context doesn't contain relevant info, output ONLY the number: 1

QUESTION: {question}

CONTEXT:
{context[:2000]}

ANSWER: {answer}

Your output must be ONLY a single digit: 0 or 1"""
    try:
        res = llm.invoke(prompt).content.strip()
        score = extract_score(res)
        return score
    except Exception as e:
        print(f"  [Faithfulness ERROR] {e}")
        return 0.0


def evaluate_answer_relevancy(question: str, answer: str) -> float:
    """Judge whether the answer directly addresses the question."""
    prompt = f"""You are an evaluation judge. Given a QUESTION and ANSWER, determine if the ANSWER directly addresses the QUESTION.

Rules:
- If the answer provides relevant information that addresses the question's intent, output ONLY: 1
- If the answer is off-topic, generic filler, or doesn't address the question, output ONLY: 0
- If the answer honestly says "I don't have enough info", that still counts as relevant (output 1) because it's not misleading.

QUESTION: {question}
ANSWER: {answer}

Your output must be ONLY a single digit: 0 or 1"""
    try:
        res = llm.invoke(prompt).content.strip()
        score = extract_score(res)
        return score
    except Exception as e:
        print(f"  [Relevancy ERROR] {e}")
        return 0.0


def precision_at_k(retrieved_ids: list, expected_ids: list, k: int = 3) -> float:
    """Calculate precision@k: fraction of top-k retrieved that are in expected set."""
    if not expected_ids:
        return 1.0  # No expectation → trivially correct
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for rid in top_k if rid in expected_ids)
    return hits / len(top_k)


def recall_at_k(retrieved_ids: list, expected_ids: list, k: int = 5) -> float:
    """Calculate recall@k: fraction of expected sources found in top-k retrieved."""
    if not expected_ids:
        return 1.0
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for eid in expected_ids if eid in top_k)
    return hits / len(expected_ids)


def run_evaluation():
    with open("eval/golden_dataset.json", "r") as f:
        dataset = json.load(f)

    print(f"=== RAG Evaluation Harness ===")
    print(f"Dataset: {len(dataset)} questions")
    print(f"Judge LLM: qwen/qwen3.6-27b via Groq")
    print(f"{'='*50}\n")

    results = []

    for i, item in enumerate(dataset):
        q = item["question"]
        print(f"[{i+1}/{len(dataset)}] {q}")

        # Call the RAG API
        start = time.time()
        try:
            res = requests.post(API_URL, json={"query": q}, timeout=60)
        except Exception as e:
            print(f"  API call failed: {e}")
            continue

        if res.status_code != 200:
            print(f"  API error: {res.status_code}")
            continue

        data = res.json()
        answer = data["answer"]
        sources = data.get("sources", [])
        retrieved_ids = [s.get("id") for s in sources]
        latency = time.time() - start
        cached = data.get("cached", False)

        # Fetch ACTUAL chunk text from DB for context (not just titles)
        context = get_chunk_texts_for_sources(retrieved_ids) if retrieved_ids else ""

        # Score
        faith = evaluate_faithfulness(q, answer, context)
        relev = evaluate_answer_relevancy(q, answer)
        p3 = precision_at_k(retrieved_ids, item.get("expected_source_ids", []), k=3)
        r5 = recall_at_k(retrieved_ids, item.get("expected_source_ids", []), k=5)

        results.append({
            "question": q,
            "answer_snippet": answer[:150],
            "retrieved_source_ids": retrieved_ids,
            "expected_source_ids": item.get("expected_source_ids", []),
            "faithfulness": faith,
            "answer_relevancy": relev,
            "precision_at_3": p3,
            "recall_at_5": r5,
            "latency_s": round(latency, 2),
            "cached": cached,
        })

        print(f"  Faith={faith:.0f} | Relev={relev:.0f} | P@3={p3:.2f} | R@5={r5:.2f} | {latency:.1f}s {'(cached)' if cached else ''}")

        time.sleep(1.5)  # Rate limit guard for Groq judge calls

    # Aggregate
    n = len(results)
    if n == 0:
        print("No results to aggregate.")
        return

    avg = lambda key: sum(r[key] for r in results) / n

    summary = {
        "run_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "num_questions": n,
        "aggregate_metrics": {
            "faithfulness": round(avg("faithfulness"), 3),
            "answer_relevancy": round(avg("answer_relevancy"), 3),
            "precision_at_3": round(avg("precision_at_3"), 3),
            "recall_at_5": round(avg("recall_at_5"), 3),
            "avg_latency_s": round(avg("latency_s"), 2),
        },
        "per_question": results,
    }

    with open("eval/eval_results.json", "w") as f:
        json.dump(summary, f, indent=4)

    print(f"\n{'='*50}")
    print(f"RESULTS ({n} questions)")
    print(f"{'='*50}")
    print(f"  Faithfulness:      {summary['aggregate_metrics']['faithfulness']:.3f}")
    print(f"  Answer Relevancy:  {summary['aggregate_metrics']['answer_relevancy']:.3f}")
    print(f"  Precision@3:       {summary['aggregate_metrics']['precision_at_3']:.3f}")
    print(f"  Recall@5:          {summary['aggregate_metrics']['recall_at_5']:.3f}")
    print(f"  Avg Latency:       {summary['aggregate_metrics']['avg_latency_s']:.2f}s")
    print(f"\nSaved to eval/eval_results.json")


if __name__ == "__main__":
    run_evaluation()
