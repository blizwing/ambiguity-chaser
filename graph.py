from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from pydantic import BaseModel
from llm_client import call_deepseek_json
from schemas import TestCase, validate_response

class GraphState(BaseModel):
    requirement: str
    status: str | None = None
    test_case: dict | None = None

with open("prompts/testcase_v1.txt", mode="r", encoding="utf-8") as f:
    PROMPT_TEMPLATE = f.read()

def generate_test_case(state: GraphState) -> dict:
    prompt = PROMPT_TEMPLATE.format(requirement=state.requirement)
    result = call_deepseek_json(prompt)
    status, detail = validate_response(result.text, TestCase)

    if status == "valid":
        return {"status": status, "test_case": detail.model_dump()}
    return {"status": status, "test_case": None}


# Graph
builder = StateGraph(GraphState)
builder.add_node("generate_test_case", generate_test_case)
builder.add_edge(START, "generate_test_case")
builder.add_edge("generate_test_case", END)
compiled = builder.compile()

if __name__ == "__main__":
    result = compiled.invoke({"requirement": "The system must lock a user account after 5 failed login attempts."})
    print(result)   