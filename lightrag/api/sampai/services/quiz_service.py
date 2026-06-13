"""Per-file adaptive quiz: difficulty inference, generation, deterministic grading.

Difficulty is mapped to retrieval breadth exactly like the original SAMpai feature:
harder quizzes draw on deeper multi-hop context. We reuse the research module's
custom BFS arm (``retrieve_mix_arm``, easy→1 / medium→2 / hard→3 hops) **read-only**,
scoped to the single file's doc, then generate MCQ/True-False with one grounded LLM
call. Grading is deterministic (exact match). The cross-file quiz and the mix-vs-naive
research pipeline are deliberately NOT used here — they arrive later as separate features.
"""

from __future__ import annotations

import logging
import os
import time

import json_repair
from sqlalchemy import func, select

from lightrag.api.sampai.db import get_sessionmaker
from lightrag.api.sampai.models.chat import ChatMessage, MessageRole
from lightrag.api.sampai.models.quiz import Quiz, QuizAttempt, QuizDifficulty, QuizStatus
from lightrag.api.sampai.services.engine_access import get_engine

logger = logging.getLogger("sampai.quiz")

_SEED = (
    "The key concepts, definitions, relationships, mechanisms, and reasoning in this "
    "document. Cover the major topics needed to test understanding."
)

# Reasoning emphasis per difficulty (the linguistic dimension; hop depth is the structural one).
_REASONING = {
    "easy": "factual recall and definitions",
    "medium": "comparison, classification, and conceptual understanding",
    "hard": "causal, multi-step, and analytical reasoning that connects several ideas",
}


# ── difficulty inference ──────────────────────────────────────────────────────
async def infer_difficulty(db, user_id: int, file_id: int) -> tuple[QuizDifficulty, str]:
    """Infer difficulty from the student's last 3 scores on this file, else their
    chat engagement. Returns (difficulty, source) where source ∈ inferred|baseline."""
    scores = (
        await db.execute(
            select(QuizAttempt.score)
            .where(QuizAttempt.user_id == user_id, QuizAttempt.file_id == file_id)
            .order_by(QuizAttempt.submitted_at.desc())
            .limit(3)
        )
    ).scalars().all()
    if scores:
        avg = sum(scores) / len(scores)
        if avg >= 0.8:
            return QuizDifficulty.HARD, "inferred"
        if avg <= 0.5:
            return QuizDifficulty.EASY, "inferred"
        return QuizDifficulty.MEDIUM, "inferred"

    # No prior attempts — fall back to chat engagement with this file.
    turns = await db.scalar(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.user_id == user_id,
            ChatMessage.file_id == file_id,
            ChatMessage.role == MessageRole.USER,
        )
    )
    if (turns or 0) >= 8:
        return QuizDifficulty.MEDIUM, "inferred"
    if (turns or 0) >= 1:
        return QuizDifficulty.EASY, "inferred"
    return QuizDifficulty.MEDIUM, "baseline"  # cold start


# ── question validation / parsing ─────────────────────────────────────────────
def _parse_json(text: str) -> object:
    t = (text or "").strip()
    if t.startswith("```"):
        t = "\n".join(t.split("\n")[1:])
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    try:
        parsed = json_repair.loads(t)
    except Exception:
        return []
    if isinstance(parsed, dict):
        parsed = parsed.get("questions", [])
    return parsed if isinstance(parsed, list) else []


def _valid_questions(raw: object, want: int) -> list[dict]:
    """Validate + normalize LLM output into stored questions (full, with answers)."""
    out: list[dict] = []
    for q in raw if isinstance(raw, list) else []:
        if not isinstance(q, dict):
            continue
        qtype = str(q.get("type", "")).lower()
        question = q.get("question", "")
        explanation = q.get("explanation", "")
        if not (isinstance(question, str) and question.strip()):
            continue
        if qtype == "mcq":
            options = q.get("options")
            ans = q.get("answer_index", q.get("answer"))
            if not (isinstance(options, list) and 2 <= len(options) <= 6):
                continue
            options = [str(o).strip() for o in options if str(o).strip()]
            if len(options) < 2:
                continue
            if not isinstance(ans, int) or not (0 <= ans < len(options)):
                continue
            out.append({
                "id": f"q{len(out) + 1}",
                "type": "mcq",
                "question": question.strip(),
                "options": options,
                "answer": ans,
                "explanation": str(explanation).strip(),
            })
        elif qtype in ("tf", "true_false", "truefalse", "boolean"):
            ans = q.get("answer")
            if isinstance(ans, str):
                ans = ans.strip().lower() in ("true", "t", "yes")
            if not isinstance(ans, bool):
                continue
            out.append({
                "id": f"q{len(out) + 1}",
                "type": "tf",
                "question": question.strip(),
                "options": [],
                "answer": ans,
                "explanation": str(explanation).strip(),
            })
        if len(out) >= want:
            break
    return out


def _system_prompt(n: int, difficulty: str) -> str:
    reasoning = _REASONING.get(difficulty, _REASONING["medium"])
    return (
        "You are an expert teacher writing a quiz GROUNDED ONLY in the provided context.\n"
        f'Output STRICT JSON only: {{"questions": [...]}} with EXACTLY {n} entries.\n'
        "Each entry is one of:\n"
        '  MCQ: {"type":"mcq","question":"...","options":["A","B","C","D"],'
        '"answer_index":<0-based index of the correct option>,"explanation":"..."}\n'
        '  True/False: {"type":"tf","question":"...","answer":true|false,"explanation":"..."}\n'
        "Rules:\n"
        f"- Difficulty is {difficulty}: emphasize {reasoning}.\n"
        "- Mix MCQ and True/False (roughly 70% MCQ, 30% True/False).\n"
        "- MCQ: exactly one correct option; 3-4 plausible, non-overlapping distractors.\n"
        "- Every question and answer MUST be answerable from the context; never invent facts.\n"
        "- 'explanation' justifies the correct answer in 1-2 sentences from the context.\n"
        "- Do not reference 'the document/context/passage' in the question text.\n"
        "Output JSON only — no markdown fences."
    )


async def _generate(engine, context: str, n: int, difficulty: str) -> list[dict]:
    raw = await engine.llm_model_func(
        f"N: {n}\nDIFFICULTY: {difficulty}\nCONTEXT:\n{context}",
        system_prompt=_system_prompt(n, difficulty),
    )
    qs = _valid_questions(_parse_json(raw), n)
    if len(qs) < n:
        missing = n - len(qs)
        logger.info("quiz: retry to fill %d missing questions", missing)
        try:
            raw2 = await engine.llm_model_func(
                f"N: {missing}\nDIFFICULTY: {difficulty}\nCONTEXT:\n{context}",
                system_prompt=_system_prompt(missing, difficulty),
            )
            for q in _valid_questions(_parse_json(raw2), missing):
                q["id"] = f"q{len(qs) + 1}"
                qs.append(q)
        except Exception:
            logger.warning("quiz retry failed", exc_info=True)
    return qs[:n]


# ── background generation ─────────────────────────────────────────────────────
async def generate_quiz_task(quiz_id: int, classroom_id: int, file_id: int, doc_id: str | None):
    from lightrag.quiz.retrieval import retrieve_mix_arm

    sm = get_sessionmaker()
    async with sm() as db:
        quiz = await db.get(Quiz, quiz_id)
        if quiz is None:
            return
        quiz.status = QuizStatus.GENERATING
        difficulty = quiz.difficulty.value
        num_questions = quiz.num_questions
        await db.commit()

    try:
        engine = await get_engine(classroom_id)
        doc_ids = {doc_id} if doc_id else set()
        # Difficulty → multi-hop breadth (easy 1 / medium 2 / hard 3), scoped to this file.
        ctx = await retrieve_mix_arm(engine, _SEED, difficulty, doc_ids)
        if ctx.is_empty():
            raise RuntimeError("No content retrieved for this file")
        context = ctx.format_for_prompt()

        t0 = time.time()
        questions = await _generate(engine, context, num_questions, difficulty)
        if len(questions) < num_questions:
            raise RuntimeError(
                f"LLM produced only {len(questions)} valid questions; expected {num_questions}"
            )

        from datetime import datetime

        async with sm() as db:
            quiz = await db.get(Quiz, quiz_id)
            if quiz is None:
                return
            quiz.questions = {"questions": questions}
            quiz.status = QuizStatus.READY
            quiz.ready_at = datetime.utcnow()
            quiz.generation_meta = {
                "hop_depth": ctx.hop_depth,
                "source_documents": ctx.source_documents,
                "entity_count": len(ctx.entities),
                "relation_count": len(ctx.relations),
                "chunk_count": ctx.chunk_count,
                "difficulty": difficulty,
                "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                "elapsed_s": round(time.time() - t0, 2),
            }
            await db.commit()
        logger.info("quiz %s ready (%d questions, hop_depth=%s)", quiz_id, len(questions), ctx.hop_depth)
    except Exception as exc:
        logger.exception("quiz %s failed", quiz_id)
        async with sm() as db:
            quiz = await db.get(Quiz, quiz_id)
            if quiz is not None:
                quiz.status = QuizStatus.FAILED
                quiz.error_msg = str(exc)[:500]
                await db.commit()


# ── deterministic grading ─────────────────────────────────────────────────────
def grade(stored_questions: list[dict], submitted: dict[str, dict]) -> dict:
    """Grade by exact match. `submitted` maps question_id → {answer_index, answer_bool}."""
    review: list[dict] = []
    correct_count = 0
    for q in stored_questions:
        qid = q["id"]
        given = submitted.get(qid) or {}
        correct_answer = q["answer"]
        if q["type"] == "mcq":
            user_answer = given.get("answer_index")
            is_correct = isinstance(user_answer, int) and not isinstance(user_answer, bool) and user_answer == correct_answer
        else:  # tf
            user_answer = given.get("answer_bool")
            is_correct = isinstance(user_answer, bool) and user_answer == correct_answer
        if is_correct:
            correct_count += 1
        review.append({
            "id": qid,
            "type": q["type"],
            "question": q["question"],
            "options": q.get("options", []),
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "correct": is_correct,
            "explanation": q.get("explanation", ""),
        })
    total = len(stored_questions)
    return {
        "score": round(correct_count / total, 4) if total else 0.0,
        "correct_count": correct_count,
        "total_count": total,
        "answers": review,
    }


def public_questions(stored_questions: list[dict]) -> list[dict]:
    """Strip answers/explanations for the pre-submit view."""
    return [
        {"id": q["id"], "type": q["type"], "question": q["question"], "options": q.get("options", [])}
        for q in stored_questions
    ]
