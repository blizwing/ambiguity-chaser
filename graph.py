from langgraph.graph import StateGraph, START, END
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
    return "ask_clarifying_questions"


def generate_test_case(state: GraphState) -> dict:
    prompt = TESTCASE_PROMPT.format(requirement=state.requirement)
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


def ask_clarifying_questions(state: GraphState) -> dict:
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


# Graph
builder = StateGraph(GraphState)
builder.add_node("score_testability", score_testability)
builder.add_node("generate_test_case", generate_test_case)
builder.add_node("ask_clarifying_questions", ask_clarifying_questions)

builder.add_edge(START, "score_testability")
builder.add_conditional_edges(
    "score_testability",
    route_by_testability,
    {
        "generate_test_case": "generate_test_case",
        "ask_clarifying_questions": "ask_clarifying_questions",
    },
)
builder.add_edge("generate_test_case", END)
builder.add_edge("ask_clarifying_questions", END)
compiled = builder.compile()

if __name__ == "__main__":
    clear_result = compiled.invoke(
        {"requirement": "The system must lock a user account after 5 failed login attempts."}
    )
    print("CLEAR REQUIREMENT:", clear_result)

    vague_result = compiled.invoke({"requirement": "The system should be fast."})
    print("VAGUE REQUIREMENT:", vague_result)
