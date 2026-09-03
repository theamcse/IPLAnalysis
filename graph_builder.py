import os
import pandas as pd
import networkx as nx
from typing import Dict, List, Tuple, Any, Optional

class IPLGraphBuilder:
    def __init__(self, data_dir: str = "d:/IPLAnalysis"):
        self.data_dir = data_dir
        self.G = nx.Graph()
        
        # Mappings
        self.player_name_to_id: Dict[str, int] = {}
        self.player_id_to_name: Dict[int, str] = {}
        self.player_full_name_to_short: Dict[str, str] = {}
        self.team_id_to_name: Dict[int, str] = {}
        self.team_name_to_id: Dict[str, int] = {}
        self.alias_to_team_id: Dict[str, int] = {}
        
        # DataFrames for analytics
        self.players_df: Optional[pd.DataFrame] = None
        self.matches_df: Optional[pd.DataFrame] = None
        self.ball_by_ball_df: Optional[pd.DataFrame] = None
        self.teams_df: Optional[pd.DataFrame] = None
        self.team_aliases_df: Optional[pd.DataFrame] = None

    def load_data(self):
        print("Loading CSV files...")
        self.players_df = pd.read_csv(os.path.join(self.data_dir, "players-data-updated.csv"))
        self.matches_df = pd.read_csv(os.path.join(self.data_dir, "ipl_matches_data.csv"))
        self.teams_df = pd.read_csv(os.path.join(self.data_dir, "teams_data.csv"))
        
        # Handle team aliases which might have double quotes in columns
        alias_path = os.path.join(self.data_dir, "team_aliases.csv")
        self.team_aliases_df = pd.read_csv(alias_path)
        # Clean column names in case they have quotes
        self.team_aliases_df.columns = [c.replace('"', '').strip() for c in self.team_aliases_df.columns]
        
        # Load deliveries (optimize memory usage by setting downcast/dtypes if needed)
        self.ball_by_ball_df = pd.read_csv(os.path.join(self.data_dir, "ball_by_ball_data.csv"))
        
        # Populate players mapping
        for _, row in self.players_df.iterrows():
            pid = int(row['player_id'])
            pname = str(row['player_name']).strip()
            pfname = str(row['player_full_name']).strip() if pd.notna(row['player_full_name']) else pname
            self.player_name_to_id[pname] = pid
            self.player_id_to_name[pid] = pname
            self.player_full_name_to_short[pfname.lower()] = pname
            
        # Populate teams mapping
        for _, row in self.teams_df.iterrows():
            tid = int(row['team_id'])
            tname = str(row['team_name']).strip()
            self.team_id_to_name[tid] = tname
            self.team_name_to_id[tname] = tid
            
        # Populate aliases mapping
        for _, row in self.team_aliases_df.iterrows():
            tid = int(row['team_id'])
            alias = str(row['alias_name']).replace('"', '').strip()
            self.alias_to_team_id[alias.upper()] = tid
            
        print("Data loaded successfully.")

    def build_graph(self):
        print("Building in-memory knowledge graph...")
        self.G.clear()
        
        # 1. Add Team Nodes
        for _, row in self.teams_df.iterrows():
            tname = str(row['team_name']).strip()
            self.G.add_node(tname, type='team', team_id=int(row['team_id']))
            
        # 2. Add Player Nodes
        for _, row in self.players_df.iterrows():
            pname = str(row['player_name']).strip()
            self.G.add_node(pname, type='player',
                            player_id=int(row['player_id']),
                            bat_style=row.get('bat_style', ''),
                            bowl_style=row.get('bowl_style', ''),
                            player_full_name=row.get('player_full_name', ''))
                            
        # 3. Add Match Nodes
        for _, row in self.matches_df.iterrows():
            mid = int(row['match_id'])
            season = str(row['season']).strip()
            venue = str(row.get('venue', '')).strip()
            city = str(row.get('city', '')).strip()
            match_date = str(row.get('match_date', ''))
            
            self.G.add_node(mid, type='match',
                            season=season,
                            venue=venue,
                            city=city,
                            match_date=match_date)
            
            # Connect teams to the matches they participated in
            t1_name = self.team_id_to_name.get(int(row['team1']))
            t2_name = self.team_id_to_name.get(int(row['team2']))
            
            if t1_name:
                self.G.add_edge(t1_name, mid, relation='played_in')
            if t2_name:
                self.G.add_edge(t2_name, mid, relation='played_in')

        # 4. Connect Players to Matches and Teams
        # Get unique (match_id, player_name, team_id) from batters and bowlers
        batters_df = self.ball_by_ball_df[['match_id', 'batter', 'team_batting']].drop_duplicates()
        bowlers_df = self.ball_by_ball_df[['match_id', 'bowler', 'team_bowling']].drop_duplicates()
        
        # Combine player match appearances
        appearances = []
        for _, row in batters_df.iterrows():
            appearances.append((int(row['match_id']), str(row['batter']).strip(), int(row['team_batting'])))
        for _, row in bowlers_df.iterrows():
            appearances.append((int(row['match_id']), str(row['bowler']).strip(), int(row['team_bowling'])))
            
        # Remove duplicate player-match appearances
        appearances = list(set(appearances))
        
        for mid, pname, tid in appearances:
            tname = self.team_id_to_name.get(tid)
            if pname in self.G and mid in self.G:
                # Edge from Player to Match with metadata about team
                self.G.add_edge(pname, mid, relation='played_match', team_name=tname)
                
                # Direct player to team mapping edge
                if tname and tname in self.G:
                    if self.G.has_edge(pname, tname):
                        self.G[pname][tname]['weight'] = self.G[pname][tname].get('weight', 1) + 1
                    else:
                        self.G.add_edge(pname, tname, relation='played_for', weight=1)
                        
        # 5. Connect dismissals (Player A dismissed by Player B)
        # Find wickets from ball_by_ball
        wickets_df = self.ball_by_ball_df[self.ball_by_ball_df['is_wicket'] == True]
        for _, row in wickets_df.iterrows():
            batter = str(row['batter']).strip()
            bowler = str(row['bowler']).strip()
            player_out = str(row['player_out']).strip() if pd.notna(row['player_out']) else ""
            kind = str(row['wicket_kind']).strip() if pd.notna(row['wicket_kind']) else "out"
            
            # If a batter got out to a bowler (e.g. bowled, caught, lbw, stumped)
            if player_out and bowler and batter in self.G and bowler in self.G:
                # We can add an edge representing dismissal
                # Note: To avoid cluttering the simple Graph, we can keep direct dismissals as edge properties, 
                # or add a directed graph. But for connectivity, a standard edge with attributes is fine.
                if self.G.has_edge(batter, bowler):
                    self.G[batter][bowler]['dismissals'] = self.G[batter][bowler].get('dismissals', 0) + 1
                else:
                    self.G.add_edge(batter, bowler, relation='dismissed_by', dismissals=1, kind=kind)

        print(f"Graph built with {self.G.number_of_nodes()} nodes and {self.G.number_of_edges()} edges.")

    # --- Search & Path Finding Helpers ---
    
    def resolve_player_name(self, name_query: str) -> Optional[str]:
        """Resolves fuzzy player name search to exact short name (node ID)"""
        q = name_query.strip().lower()
        if not q:
            return None
            
        # 1. Exact match in keys
        for key in self.player_name_to_id.keys():
            if key.lower() == q:
                return key
                
        # 2. Match in full name map
        if q in self.player_full_name_to_short:
            return self.player_full_name_to_short[q]
            
        # 3. Substring match on player name (e.g., 'Dhoni' -> 'MS Dhoni')
        matches = []
        for key in self.player_name_to_id.keys():
            if q in key.lower():
                matches.append(key)
        if matches:
            matches.sort(key=len)
            return matches[0]
            
        # 4. Substring match on full name
        for fname, sname in self.player_full_name_to_short.items():
            if q in fname:
                matches.append(sname)
        if matches:
            matches.sort(key=len)
            return matches[0]
            
        # 5. Tokenized word-match intersection
        words = [w for w in q.split() if len(w) > 1]
        if not words:
            return None
            
        # Check if all query words exist in player name
        for key in self.player_name_to_id.keys():
            key_lower = key.lower()
            if all(w in key_lower for w in words):
                return key
                
        # Check if all query words exist in full name
        for fname, sname in self.player_full_name_to_short.items():
            if all(w in fname for w in words):
                return sname
                
        return None

    def resolve_team_name(self, team_query: str) -> Optional[str]:
        """Resolves fuzzy team name/alias to exact team name"""
        q = team_query.strip().upper()
        if not q:
            return None
            
        # Check alias map
        if q in self.alias_to_team_id:
            tid = self.alias_to_team_id[q]
            return self.team_id_to_name.get(tid)
            
        # Check standard name map
        for tname in self.team_name_to_id.keys():
            if q in tname.upper():
                return tname
                
        return None

    def get_shortest_connection(self, player1_query: str, player2_query: str) -> Dict[str, Any]:
        """Finds the shortest path connection between two players"""
        p1 = self.resolve_player_name(player1_query)
        p2 = self.resolve_player_name(player2_query)
        
        if not p1 or not p2:
            return {
                "success": False,
                "error": f"Could not resolve players: '{player1_query}' -> {p1}, '{player2_query}' -> {p2}"
            }
            
        if p1 == p2:
            return {
                "success": True,
                "path": [p1],
                "explanation": f"{p1} and {p2} are the same player."
            }
            
        try:
            path = nx.shortest_path(self.G, source=p1, target=p2)
            
            # Build detailed explanation
            steps = []
            for i in range(len(path) - 1):
                node_a = path[i]
                node_b = path[i+1]
                edge_data = self.G[node_a][node_b]
                
                type_a = self.G.nodes[node_a].get('type')
                type_b = self.G.nodes[node_b].get('type')
                
                if type_a == 'player' and type_b == 'team':
                    steps.append(f"{node_a} played for {node_b}")
                elif type_a == 'team' and type_b == 'player':
                    steps.append(f"{node_a} had player {node_b}")
                elif type_a == 'player' and type_b == 'match':
                    team_name = edge_data.get('team_name', 'a team')
                    steps.append(f"{node_a} played in Match ID {node_b} for {team_name}")
                elif type_a == 'match' and type_b == 'player':
                    team_name = edge_data.get('team_name', 'a team')
                    steps.append(f"Match ID {node_a} featured player {node_b} playing for {team_name}")
                elif type_a == 'team' and type_b == 'match':
                    steps.append(f"{node_a} participated in Match ID {node_b}")
                elif type_a == 'match' and type_b == 'team':
                    steps.append(f"Match ID {node_a} featured {node_b}")
                elif type_a == 'player' and type_b == 'player':
                    # Dismissal connection
                    steps.append(f"{node_a} has match-up relation with {node_b} (dismissals: {edge_data.get('dismissals', 1)})")
                    
            explanation = " -> ".join(str(node) for node in path) + " | Connections: " + ", ".join(steps)
            return {
                "success": True,
                "path": [str(n) for n in path],
                "explanation": explanation
            }
            
        except nx.NetworkXNoPath:
            return {
                "success": False,
                "error": f"No path found between {p1} and {p2}."
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error running pathfind: {str(e)}"
            }

    def get_player_stats_summary(self, player_query: str) -> Dict[str, Any]:
        """Returns brief graph-based connections for a player"""
        pname = self.resolve_player_name(player_query)
        if not pname or pname not in self.G:
            return {"success": False, "error": f"Player '{player_query}' not found."}
            
        node_data = self.G.nodes[pname]
        neighbors = list(self.G.neighbors(pname))
        
        teams = [n for n in neighbors if self.G.nodes[n].get('type') == 'team']
        matches = [n for n in neighbors if self.G.nodes[n].get('type') == 'match']
        matchups = [n for n in neighbors if self.G.nodes[n].get('type') == 'player']
        
        return {
            "success": True,
            "player_name": pname,
            "full_name": node_data.get('player_full_name', ''),
            "bat_style": node_data.get('bat_style', ''),
            "bowl_style": node_data.get('bowl_style', ''),
            "teams_played_for": teams,
            "total_matches_played": len(matches),
            "head_to_head_players": matchups[:10]  # sample of direct matchups (dismissals)
        }
