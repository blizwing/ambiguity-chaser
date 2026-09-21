from langgraph.graph import StateGraph, START, END
from typing import TypedDict


class State(TypedDict):
    text: str

def shout(state : State) -> dict:
    print(f"Start of the Line...")
    return {"text": state["text"].upper()}

def exclaim(state: State) -> dict:
    print(f"End of the Line...")
    return {"text": state["text"] + "!"}

graph = StateGraph(State)
graph.add_node("shout", shout)
graph.add_node("exclaim", exclaim)
graph.add_edge(START, "shout")
graph.add_edge("shout", "exclaim")
graph.add_edge("exclaim", END)
compiled = graph.compile()


if __name__ == "__main__":
    result = compiled.invoke({"text": "hello"})
    print(result)