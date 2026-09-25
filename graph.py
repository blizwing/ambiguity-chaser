import hashlib
import sys

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from pydantic import BaseModel
from llm_client import call_deepseek_json
from schemas import (
    TestCase,
    TestabilityScore,
    ClarifyingQuestions,
    TESTABILITY_THRESHOLD,
    compute_testability_score,
    validate_response,
)


class GraphState(BaseModel):
    requirement: str
    status: str | None = None
    test_case: dict | None = None
    testability_score: int | None = None
    testability_detail: dict | None = None
    clarifying_questions: list[str] | None = None
    human_answer: str | None = None


with open("prompts/testcase_v1.txt", mode="r", encoding="utf-8") as f:
    TESTCASE_PROMPT = f.read()

with open("prompts/testability_score_v1.txt", mode="r", encoding="utf-8") as f:
    SCORE_PROMPT = f.read()

with open("prompts/clarifying_questions_v1.txt", mode="r", encoding="utf-8") as f:
    QUESTIONS_PROMPT = f.read()


def score_testability(state: GraphState) -> dict:
    prompt = SCORE_PROMPT.format(requirement=state.requirement)
    result = call_deepseek_json(prompt)
    status, detail = validate_response(result.text, TestabilityScore)

    if status != "valid":
        # Can't confirm testability if the scorer's own output didn't
        # validate — treat as untestable rather than crashing the graph.
        return {"status": status, "testability_score": 0, "testability_detail": None}

    return {"testability_score": compute_testability_score(detail), "testability_detail": detail.model_dump()}


def route_by_testability(state: GraphState) -> str:
    if state.testability_score is not None and state.testability_score >= TESTABILITY_THRESHOLD:
        return "generate_test_case"
    return "generate_questions"


def generate_test_case(state: GraphState) -> dict:
    requirement = state.requirement
    if state.human_answer:
        # Post-resume path: fold the human's answer in as clarifying
        # context rather than re-scoring (that's Week 10's re-ask loop,
        # out of scope here — Week 9 proves the pause/resume loop works).
        requirement = f"{requirement}\nClarification: {state.human_answer}"

    prompt = TESTCASE_PROMPT.format(requirement=requirement)
    result = call_deepseek_json(prompt)
    status, detail = validate_response(result.text, TestCase)

    if status == "valid":
        return {"status": status, "test_case": detail.model_dump()}
    return {"status": status, "test_case": None}


def _describe_issues(detail: dict | None) -> str:
    if detail is None:
        return "could not confirm the requirement contains a measurable condition"

    issues = []
    if not detail["has_measurable_condition"]:
        issues.append("no measurable or verifiable condition")
    if detail["has_vague_qualitative_language"]:
        issues.append("relies on vague qualitative language")
    if detail["has_ambiguous_scope"]:
        issues.append("expected outcome is ambiguous")
    if detail["missing_precondition"]:
        issues.append("missing an explicit trigger/precondition")
    return "; ".join(issues) if issues else detail["reasoning"]


def generate_questions(state: GraphState) -> dict:
    """The 'expensive' half — LLM call, completes fully before any
    interrupt. Split out from ask_human so this never re-runs on resume
    (SESSION 4 finding: an interrupted node re-runs from its start)."""
    issues = _describe_issues(state.testability_detail)
    prompt = QUESTIONS_PROMPT.format(requirement=state.requirement, issues=issues)
    result = call_deepseek_json(prompt)
    status, detail = validate_response(result.text, ClarifyingQuestions)

    if status == "valid" and detail.questions:
        return {"status": status, "clarifying_questions": detail.questions}
    if status == "valid":
        # Schema-valid but empty — a technically-valid response with zero
        # questions isn't trustworthy for a node whose whole job is asking
        # something (same grader-integrity discipline as P1's ScoreIntegrityError).
        return {"status": "invalid", "clarifying_questions": None}
    return {"status": status, "clarifying_questions": None}


def route_after_questions(state: GraphState) -> str:
    """If question generation itself failed, stop rather than interrupting
    with nothing real to show a human — same fail-safe discipline as
    score_testability forcing 0 on its own invalid output."""
    return "ask_human" if state.status == "valid" else "end"


def ask_human(state: GraphState) -> dict:
    """Nothing but the interrupt — the SESSION 4 split. Re-runs from the
    top on every resume, but there's nothing costly here to repeat."""
    answer = interrupt(state.clarifying_questions)
    return {"human_answer": answer}


# Graph
builder = StateGraph(GraphState)
builder.add_node("score_testability", score_testability)
builder.add_node("generate_test_case", generate_test_case)
builder.add_node("generate_questions", generate_questions)
builder.add_node("ask_human", ask_human)

builder.add_edge(START, "score_testability")
builder.add_conditional_edges(
    "score_testability",
    route_by_testability,
    {
        "generate_test_case": "generate_test_case",
        "generate_questions": "generate_questions",
    },
)
builder.add_conditional_edges(
    "generate_questions",
    route_after_questions,
    {"ask_human": "ask_human", "end": END},
)
builder.add_edge("ask_human", "generate_test_case")
builder.add_edge("generate_test_case", END)


# thread_id derivation, Pratham's call: a deterministic hash of the
# requirement text, so the same requirement string always resumes the
# same paused thread without the caller having to track an id separately.
# Known tradeoff, accepted: two identical requirement strings submitted
# as separate runs collide onto the same thread.
def thread_id_for(requirement: str) -> str:
    return hashlib.sha256(requirement.encode()).hexdigest()[:16]


DB_PATH = "graph_state.db"


def _config_for(requirement: str) -> dict:
    thread_id = thread_id_for(requirement)
    print("thread_id:", thread_id)
    return {"configurable": {"thread_id": thread_id}}


def start_run(requirement: str):
    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        return graph.invoke({"requirement": requirement}, config=_config_for(requirement))


def peek(requirement: str):
    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        snapshot = graph.get_state(_config_for(requirement))
        return snapshot.values, snapshot.next, snapshot.interrupts


def resume_run(requirement: str, answer: str):
    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        return graph.invoke(Command(resume=answer), config=_config_for(requirement))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"
    requirement_arg = sys.argv[2] if len(sys.argv) > 2 else "The system should be fast."

    if mode == "start":
        print("RESULT AFTER START:", start_run(requirement_arg))
    elif mode == "peek":
        values, next_nodes, interrupts = peek(requirement_arg)
        print("STATE SNAPSHOT:", values)
        print("PENDING NEXT NODE(S):", next_nodes)
        print("PENDING INTERRUPTS:", interrupts)
    elif mode == "resume":
        answer_arg = sys.argv[3] if len(sys.argv) > 3 else "no additional context"
        print("RESULT AFTER RESUME:", resume_run(requirement_arg, answer_arg))
    else:
        raise ValueError(f"unknown mode: {mode}")
