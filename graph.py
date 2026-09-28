import hashlib
import sys

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field
from llm_client import call_deepseek_json
from schemas import (
    TestCase,
    TestabilityScore,
    ClarifyingQuestions,
    TESTABILITY_THRESHOLD,
    compute_testability_score,
    validate_response,
)


MAX_REASK_ITERATIONS = 2


class GraphState(BaseModel):
    requirement: str
    status: str | None = None
    test_case: dict | None = None
    testability_score: int | None = None
    testability_detail: dict | None = None
    clarifying_questions: list[str] | None = None
    # A list, not a single string: with re-asking (Week 10), a second round
    # must not drop the first round's answer, so every answer accumulates
    # rather than overwriting.
    human_answers: list[str] = Field(default_factory=list)
    reask_count: int = 0


with open("prompts/testcase_v1.txt", mode="r", encoding="utf-8") as f:
    TESTCASE_PROMPT = f.read()

with open("prompts/testability_score_v1.txt", mode="r", encoding="utf-8") as f:
    SCORE_PROMPT = f.read()

with open("prompts/clarifying_questions_v1.txt", mode="r", encoding="utf-8") as f:
    QUESTIONS_PROMPT = f.read()


def _fold_in_clarifications(requirement: str, answers: list[str]) -> str:
    lines = "\n".join(f"Clarification: {answer}" for answer in answers)
    return f"{requirement}\n{lines}" if answers else requirement


def score_testability(state: GraphState) -> dict:
    # Re-ask loop (Week 10): re-score with every clarification gathered so
    # far folded in — a requirement that was ambiguous the first time
    # doesn't get graded on the original text alone once clarified.
    requirement = _fold_in_clarifications(state.requirement, state.human_answers)

    prompt = SCORE_PROMPT.format(requirement=requirement)
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
    if state.reask_count >= MAX_REASK_ITERATIONS:
        # Guard exhausted: two rounds of clarification and it's still not
        # testable. Per the P1 non-fabrication principle, don't emit a
        # spec anyway — route to a human with more authority than whoever
        # answered so far, instead of guessing.
        return "mark_unresolved"
    return "generate_questions"


def generate_test_case(state: GraphState) -> dict:
    # Post-resume path: fold every clarification gathered in as context for
    # spec generation (score_testability folds the same list in separately,
    # for its own re-scoring pass). Only reached via a clean testability
    # pass — the guard-exhausted case routes to mark_unresolved instead.
    requirement = _fold_in_clarifications(state.requirement, state.human_answers)

    prompt = TESTCASE_PROMPT.format(requirement=requirement)
    result = call_deepseek_json(prompt)
    status, detail = validate_response(result.text, TestCase)

    if status != "valid":
        return {"status": status, "test_case": None}
    return {"status": status, "test_case": detail.model_dump()}


def mark_unresolved(state: GraphState) -> dict:
    """Guard-exhausted terminal state (Week 10, corrected): no test case,
    no LLM call — just a status a caller can filter on to route this
    requirement to a human with more authority than whoever answered so
    far. clarifying_questions and human_answers stay in state so whoever
    picks it up next has the full history, not a blank slate."""
    return {"status": "needs_escalation"}


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
    return {
        "human_answers": state.human_answers + [answer],
        "reask_count": state.reask_count + 1,
    }


# Graph
builder = StateGraph(GraphState)
builder.add_node("score_testability", score_testability)
builder.add_node("generate_test_case", generate_test_case)
builder.add_node("generate_questions", generate_questions)
builder.add_node("ask_human", ask_human)
builder.add_node("mark_unresolved", mark_unresolved)

builder.add_edge(START, "score_testability")
builder.add_conditional_edges(
    "score_testability",
    route_by_testability,
    {
        "generate_test_case": "generate_test_case",
        "generate_questions": "generate_questions",
        "mark_unresolved": "mark_unresolved",
    },
)
builder.add_conditional_edges(
    "generate_questions",
    route_after_questions,
    {"ask_human": "ask_human", "end": END},
)
builder.add_edge("ask_human", "score_testability")
builder.add_edge("generate_test_case", END)
builder.add_edge("mark_unresolved", END)


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
