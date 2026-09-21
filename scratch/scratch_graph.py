from langgraph.graph import StateGraph, START, END
from typing import TypedDict


class State(TypedDict):
    text: str

def shout(state : State) -> dict:
    print(f"End of the Line...")
    return {"text": state["text"].upper()}

graph = StateGraph(State)
graph.add_node("shout", shout)
graph.add_edge(START, "shout")
graph.add_edge("shout", END)
compiled = graph.compile()


if __name__ == "__main__":
    result = compiled.invoke({"text": "hello"})
    print(result)