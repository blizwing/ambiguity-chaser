import sys

from pydantic import BaseModel

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(BaseModel):
    topic: str
    answer: str | None = None
    note: str | None = None


def ask(state: State) -> dict:
    print("[ask] node running, about to interrupt")
    human_answer = interrupt({"question": f"What tone should the note about '{state.topic}' use?"})
    print("[ask] resumed with:", human_answer)
    return {"answer": human_answer}


def finalize(state: State) -> dict:
    print("[finalize] node running")
    return {"note": f"A {state.answer} note about {state.topic}."}


builder = StateGraph(State)
builder.add_node("ask", ask)
builder.add_node("finalize", finalize)
builder.add_edge(START, "ask")
builder.add_edge("ask", "finalize")
builder.add_edge("finalize", END)

DB_PATH = "scratch/interrupt_demo.db"
THREAD_ID = "demo-thread-1"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "start"

    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": THREAD_ID}}

        if mode == "start":
            result = graph.invoke({"topic": "the Q3 release delay"}, config=config)
            print("RESULT AFTER START:", result)

        elif mode == "peek":
            snapshot = graph.get_state(config)
            print("STATE SNAPSHOT:", snapshot.values)
            print("PENDING NEXT NODE(S):", snapshot.next)
            print("PENDING INTERRUPTS:", snapshot.interrupts)

        elif mode == "resume":
            answer = sys.argv[2] if len(sys.argv) > 2 else "apologetic"
            result = graph.invoke(Command(resume=answer), config=config)
            print("RESULT AFTER RESUME:", result)

        else:
            raise ValueError(f"unknown mode: {mode}")


if __name__ == "__main__":
    main()
