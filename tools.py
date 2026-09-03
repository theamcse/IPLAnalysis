import io
import os
import sys
import time
import traceback
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for server environment
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from langchain.tools import tool
from graph_builder import IPLGraphBuilder

def get_tools(builder: IPLGraphBuilder):
    
    @tool("resolve_team_alias")
    def resolve_team_alias(team_query: str) -> str:
        """
        Resolves abbreviations or nick names of IPL teams to their official team name.
        Use this first if the user refers to teams by short codes (e.g. 'RCB', 'CSK', 'MI', 'KKR', 'DC', 'KXIP', 'SRH', 'RR').
        Args:
            team_query: The short code or nickname of the team (e.g., 'RCB').
        """
        resolved = builder.resolve_team_name(team_query)
        if resolved:
            return f"Official Name: '{resolved}'"
        return f"Could not resolve team: '{team_query}'"

    @tool("query_knowledge_graph")
    def query_knowledge_graph(action: str, query_param1: str, query_param2: str = "") -> str:
        """
        Queries the IPL Knowledge Graph for player-team connections, teammate relationships, or path connections.
        Supported actions:
        1. 'shortest_path': Finds the connection path between two players. Requires both query_param1 (Player A) and query_param2 (Player B).
        2. 'player_summary': Returns a player's profile and lists of teams and matches. Requires query_param1 (Player Name).
        """
        action = action.strip().lower()
        if action == "shortest_path":
            if not query_param2:
                return "Error: shortest_path requires two player names (query_param1 and query_param2)."
            res = builder.get_shortest_connection(query_param1, query_param2)
            if res.get("success"):
                return f"Path found:\n{res['explanation']}"
            else:
                return f"Path query failed: {res.get('error')}"
                
        elif action == "player_summary":
            res = builder.get_player_stats_summary(query_param1)
            if res.get("success"):
                return (
                    f"Player: {res['player_name']} ({res['full_name']})\n"
                    f"Batting Style: {res['bat_style']}\n"
                    f"Bowling Style: {res['bowl_style']}\n"
                    f"Teams played for: {', '.join(res['teams_played_for'])}\n"
                    f"Total matches played: {res['total_matches_played']}\n"
                    f"Match-up connections: {', '.join(res['head_to_head_players'])}"
                )
            else:
                return f"Summary failed: {res.get('error')}"
        else:
            return f"Unsupported action: '{action}'. Use 'shortest_path' or 'player_summary'."

    @tool("query_pandas_stats")
    def query_pandas_stats(python_code: str) -> str:
        """
        Runs Python code against IPL DataFrames to perform statistical, math, filter, or chart/graph operations.
        Available variables in local scope:
        - `players_df`: player profiles (player_id, player_name, bat_style, bowl_style, player_full_name)
        - `matches_df`: match statistics (match_id, season, venue, toss_winner, team1, team2, toss_decision, match_winner, win_by_runs, win_by_wickets, player_of_match)
        - `ball_by_ball_df`: detailed balls (match_id, batter, bowler, team_batting, team_bowling, batter_runs, extras, total_runs, is_wicket, is_wide_ball, is_no_ball, wicket_kind)
        - `teams_df`: team metadata (team_id, team_name)
        - `team_aliases_df`: team abbreviations (alias_name, team_id)

        Rules for Python code:
        1. Always format output using print statements. E.g. print(df.groupby(...))
        2. To draw charts, create a matplotlib or seaborn figure (e.g., plt.figure(figsize=(10,6))), plot the chart, and do NOT call plt.show(). The system will automatically save it.
        3. Make sure to use team IDs for queries on teams in matches_df (e.g. team1, team2, match_winner, toss_winner are IDs, not names). Map names to IDs using teams_df or resolve_team_alias.
        """
        # Ensure we have the clean code string
        code_str = python_code.strip()
        # Remove markdown code block wraps if LLM sends them
        if code_str.startswith("```python"):
            code_str = code_str[9:]
        if code_str.endswith("```"):
            code_str = code_str[:-3]
        code_str = code_str.strip()

        # Clear matplotlib figures before running
        plt.clf()
        plt.close('all')

        # Define execution scope
        local_scope = {
            'pd': pd,
            'plt': plt,
            'sns': sns,
            'players_df': builder.players_df,
            'matches_df': builder.matches_df,
            'ball_by_ball_df': builder.ball_by_ball_df,
            'teams_df': builder.teams_df,
            'team_aliases_df': builder.team_aliases_df
        }

        # Redirect stdout
        old_stdout = sys.stdout
        redirected_output = sys.stdout = io.StringIO()

        try:
            # Execute python code
            exec(code_str, {}, local_scope)
            sys.stdout = old_stdout
            output = redirected_output.getvalue()

            # Check if a chart was generated
            if len(plt.get_fignums()) > 0:
                os.makedirs("static", exist_ok=True)
                chart_filename = f"chart_{int(time.time())}.png"
                chart_path = os.path.join("static", chart_filename)
                plt.savefig(chart_path, bbox_inches='tight')
                plt.close('all')
                output += f"\n[CHART_CREATED:{chart_filename}]"

            if not output.strip():
                return "Code executed successfully with no printed output. Make sure you use 'print()' to output results!"
            return output
        except Exception as e:
            sys.stdout = old_stdout
            tb = traceback.format_exc()
            return f"Error executing Python code: {str(e)}\nTraceback:\n{tb}"

    return [resolve_team_alias, query_knowledge_graph, query_pandas_stats]
