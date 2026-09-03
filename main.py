import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv(dotenv_path="d:/IPLAnalysis/.env", override=True)

# Map/verify API key
deepseek_key = os.getenv("DEEPSEEK_API_KEY")
if not deepseek_key or deepseek_key == "YOUR_DEEPSEEK_API_KEY_HERE":
    # Check if user put it in GEMINI_API_KEY or ANTHROPIC_API_KEY by mistake
    for key in ["GEMINI_API_KEY", "ANTHROPIC_API_KEY"]:
        val = os.getenv(key)
        if val and val.startswith("sk-") and not val.startswith("sk-ant-"):
            deepseek_key = val
            break

if deepseek_key and deepseek_key != "YOUR_DEEPSEEK_API_KEY_HERE":
    os.environ["DEEPSEEK_API_KEY"] = deepseek_key
    print("DeepSeek API Key detected and configured.")
else:
    print("WARNING: DEEPSEEK_API_KEY is not set correctly in the .env file. Please update it.")

from graph_builder import IPLGraphBuilder
from tools import get_tools

# Initialize FastAPI app
app = FastAPI(title="IPL Hybrid Analysis System")

# Ensure static directory exists for assets and generated charts
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global instances
builder = IPLGraphBuilder(data_dir="d:/IPLAnalysis")
agent_executor = None

# On startup, load data and build graph
@app.on_event("startup")
def startup_event():
    global agent_executor
    print("Starting backend server...")
    
    # 1. Load data
    builder.load_data()
    
    # 2. Build graph
    builder.build_graph()
    
    # 3. Setup LangChain agent
    from langchain_deepseek import ChatDeepSeek
    from langchain.agents import create_agent
    from langgraph.checkpoint.memory import MemorySaver
    
    llm = ChatDeepSeek(model="deepseek-chat", temperature=0)
    memory = MemorySaver()
    
    system_prompt = """You are a professional IPL data analysis assistant. You have access to a custom IPL dataset containing:
1. Tabular DataFrames of players, matches, deliveries (ball-by-ball), teams, and aliases.
2. An in-memory Knowledge Graph linking players, matches, teams, and venues.

Your goal is to answer user queries accurately by choosing the most appropriate tool.

CRITICAL: When you need to call a tool, you must output the tool call immediately. Do NOT explain what you are about to do, do NOT write plans or lists of steps, and do NOT output any conversational text before the tool call.

Tools guide:
- Always use 'resolve_team_alias' first if the user refers to teams using abbreviations or short names (e.g. 'RCB', 'CSK', 'MI', 'KKR', 'KXIP', 'SRH', 'RR', 'DC').
- For questions about connection paths between players, player profiles/teams, or teammate relationships, use the 'query_knowledge_graph' tool.
- For statistical, mathematical, aggregates, count, filtering, and chart/plot queries, use the 'query_pandas_stats' tool.

Pandas query guidelines:
- In matches_df, columns 'team1', 'team2', 'toss_winner', and 'match_winner' contain team IDs (integers), NOT team names. Map names to IDs first! E.g. find the team ID using teams_df or resolve_team_alias.
- In matches_df, the 'season' column contains string values (e.g. '2016' or '2020/21'). Always filter matches_df['season'] using string values, not integers (e.g., matches_df['season'] == '2016').
- In ball_by_ball_df, columns 'batter' and 'bowler' contain string names of players, not IDs.
- When generating charts, the 'query_pandas_stats' tool will print '[CHART_CREATED:filename.png]'. Ensure you include this tag EXACTLY in your final response if a chart was generated so the interface can render it. E.g., 'Here is the bar chart: [CHART_CREATED:chart_123.png]'.
- Present answers in a clear, formatted, user-friendly statement (or tables). Use markdown formatting for tables and bullet points. Keep it professional.
"""
    
    tools = get_tools(builder)
    agent_executor = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=memory
    )
    print("Agent executor initialized.")

class QueryRequest(BaseModel):
    query: str
    session_id: str = "default-session"

@app.post("/query")
async def execute_query(payload: QueryRequest):
    global agent_executor
    if not agent_executor:
        raise HTTPException(status_code=503, detail="Agent is not initialized yet.")
    
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    try:
        config = {"configurable": {"thread_id": payload.session_id}}
        response = agent_executor.invoke({"messages": [("user", query)]}, config=config)
        output = response["messages"][-1].content
        return {"response": output}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error executing agent query: {str(e)}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

@app.get("/data-info")
async def get_data_info():
    """Returns metadata about the loaded IPL files for the dashboard frontend"""
    try:
        info = {
            "players": {
                "count": len(builder.players_df) if builder.players_df is not None else 0,
                "columns": list(builder.players_df.columns) if builder.players_df is not None else []
            },
            "matches": {
                "count": len(builder.matches_df) if builder.matches_df is not None else 0,
                "columns": list(builder.matches_df.columns) if builder.matches_df is not None else []
            },
            "deliveries": {
                "count": len(builder.ball_by_ball_df) if builder.ball_by_ball_df is not None else 0,
                "columns": list(builder.ball_by_ball_df.columns) if builder.ball_by_ball_df is not None else []
            },
            "teams": {
                "count": len(builder.teams_df) if builder.teams_df is not None else 0,
                "columns": list(builder.teams_df.columns) if builder.teams_df is not None else []
            },
            "graph": {
                "nodes": builder.G.number_of_nodes(),
                "edges": builder.G.number_of_edges()
            }
        }
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metadata: {str(e)}")

@app.get("/")
def read_root():
    return FileResponse("index.html")
