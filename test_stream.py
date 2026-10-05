import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, MessagesState, START

async def test_stream():
    async def call_model(state, config):
        llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0, streaming=True, api_key="dummy", base_url="http://localhost:11434/v1")
        res = await llm.ainvoke(state["messages"], config=config)
        return {"messages": [res]}
        
    workflow = StateGraph(MessagesState)
    workflow.add_node("agent", call_model)
    workflow.add_edge(START, "agent")
    app_graph = workflow.compile()
    
    config = {"configurable": {"thread_id": "1"}}
    
    print("Testing stream_mode='messages'...")
    try:
        async for chunk, metadata in app_graph.astream({"messages": [HumanMessage(content="Hello")]}, config, stream_mode="messages"):
            print("CHUNK:", type(chunk), getattr(chunk, "content", chunk))
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(test_stream())
