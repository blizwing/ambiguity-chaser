import sys
import uuid

from pydantic import BaseModel

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(BaseModel):
    topic: str
    question: str | None = None
    answer: str | None = None
    note: str | None = None


def prepare_question(state: State) -> dict:
    print("[prepare_question] running, counter bump")
    with open("scratch/counter.txt", "a") as f:
        f.write("ran\n")
    return {"question": f"What tone should the note about '{state.topic}' use?"}


def ask_human(state: State) -> dict:
    print("[ask_human] node running, about to interrupt")
    human_answer = interrupt(state.question)
    print("[ask_human] resumed with:", human_answer)
    return {"answer": human_answer}


def finalize(state: State) -> dict:
    print("[finalize] node running")
    return {"note": f"A {state.answer} note about {state.topic}."}


builder = StateGraph(State)
builder.add_node("prepare_question", prepare_question)
builder.add_node("ask_human", ask_human)
builder.add_node("finalize", finalize)
builder.add_edge(START, "prepare_question")
builder.add_edge("prepare_question", "ask_human")
builder.add_edge("ask_human", "finalize")
builder.add_edge("finalize", END)

DB_PATH = "scratch/interrupt_demo.db"
THREAD_ID = "week9-test-1"


def main():
    print("THREAD_ID:", THREAD_ID)
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