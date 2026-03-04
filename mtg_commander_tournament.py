import streamlit as st
import pandas as pd
import random

# --- INITIALIZE SESSION STATE ---
if 'players' not in st.session_state:
    st.session_state.players = []
if 'history' not in st.session_state:
    st.session_state.history = []
if 'current_round' not in st.session_state:
    st.session_state.current_round = 0
if 'current_pods' not in st.session_state:
    st.session_state.current_pods = []
if 'mode' not in st.session_state:
    st.session_state.mode = "Casual"

st.set_page_config(page_title="MTG Commander Tracker", layout="wide")

# --- LOGIC FUNCTIONS ---
def generate_commander_pods():
    players = list(st.session_state.players)
    total = len(players)
    if total == 0:
        return

    # Build a history of who has played whom
    # peer_history[(player1, player2)] = number of times they've shared a pod
    peer_history = {}
    for round_data in st.session_state.history:
        for pod in round_data:
            participants = pod['players']
            for i in range(len(participants)):
                for j in range(i + 1, len(participants)):
                    pair = tuple(sorted((participants[i], participants[j])))
                    peer_history[pair] = peer_history.get(pair, 0) + 1

    # We try 100 different shuffles and pick the one with the lowest "Conflict Score"
    best_pods = []
    min_conflict = float('inf')

    for _ in range(100):
        random.shuffle(players)
        temp_players = list(players)
        current_attempt_pods = []
        current_conflict = 0

        # Determine pod sizes using your "Maximize 4s" math
        num_3s = (4 - (total % 4)) % 4
        if total == 6: num_4s, num_3s = 0, 2
        else: num_4s = (total - (num_3s * 3)) // 4

        # Simulate filling pods for this shuffle
        sizes = [4] * int(num_4s) + [3] * int(num_3s)
        
        idx = 0
        for size in sizes:
            pod = temp_players[idx : idx + size]
            current_attempt_pods.append(pod)
            # Calculate conflict for this pod
            for i in range(len(pod)):
                for j in range(i + 1, len(pod)):
                    pair = tuple(sorted((pod[i], pod[j])))
                    current_conflict += peer_history.get(pair, 0) ** 2 # Squaring punishes repeat rematches heavily
            idx += size

        if current_conflict < min_conflict:
            min_conflict = current_conflict
            best_pods = current_attempt_pods
        
        if min_conflict == 0: # Found a perfect shuffle with no rematches
            break

    st.session_state.current_pods = best_pods
    st.session_state.current_round += 1


def get_commander_standings():
    stats = {p: {'Points': 0, 'Wins': 0, 'Opponents': []} for p in st.session_state.players}
    
    for round_data in st.session_state.history:
        for entry in round_data:
            players_in_pod = entry['players']
            mode_at_time = entry.get('type', 'Casual')
            
            for p in players_in_pod:
                if p not in stats: continue
                
                if mode_at_time == "Casual":
                    stats[p]['Points'] += 1
                    if p == entry.get('winner'):
                        stats[p]['Points'] += 3
                        stats[p]['Wins'] += 1
                else:
                    # Competitive Points: 1st=5, 2nd=3, 3rd=2, 4th=1
                    rank = entry['ranks'].get(p, 4)
                    pts_map = {1: 5, 2: 3, 3: 2, 4: 1}
                    stats[p]['Points'] += pts_map.get(rank, 1)
                    if rank == 1:
                        stats[p]['Wins'] += 1
                
                others = [o for o in players_in_pod if o != p]
                stats[p]['Opponents'].extend(others)

    leaderboard = []
    for p, s in stats.items():
        omp = sum(stats[o]['Points'] for o in s['Opponents'] if o in stats)
        leaderboard.append({'Player': p, 'Points': s['Points'], 'Wins': s['Wins'], 'OMP': omp})
    
    df = pd.DataFrame(leaderboard)
    return df.sort_values(by=['Points', 'Wins', 'OMP'], ascending=False) if not df.empty else df

# --- CALLBACK FOR RAPID ENTRY ---
def add_player_callback():
    # Use the 'player_input' key to get the text
    name = st.session_state.player_input
    if name and name not in st.session_state.players:
        st.session_state.players.append(name)
    # Clear the input box by resetting the key
    st.session_state.player_input = ""

# --- SIDEBAR ---
with st.sidebar:
    st.title("🛡️ EDH Tournament")
    st.session_state.mode = st.radio("Tournament Mode", ["Casual", "Competitive"])
    st.divider()
    st.subheader("Registration")
        # Adding 'on_change' and 'key' makes hitting Enter work instantly
    st.text_input(
            "Enter Player Name:", 
            key="player_input", 
            on_change=add_player_callback,
            placeholder="Type name and hit Enter...",
            autocomplete="new-password" 
        )
        
    st.write(f"**Total Players:** {len(st.session_state.players)}")

    # Check if the tournament has NOT started yet
    if st.session_state.current_round == 0:
        if st.session_state.players:
            with st.expander("View/Remove Players"):
                for p in st.session_state.players:
                    cols = st.columns([4, 1])
                    cols[0].write(p)
                    if cols[1].button("❌", key=f"del_{p}"):
                        st.session_state.players.remove(p)
                        st.rerun()
        else:
            st.info("Waiting for players...")
    else:
        # This shows once Round 1 is generated
        st.success(f"🏆 Tournament in Progress (Round {st.session_state.current_round})")
        # You might still want to see the players, so we can keep the expander here too
        with st.expander("View Registered Players"):
            for p in st.session_state.players:
                st.text(f"• {p}")
            
        st.divider()
    if st.button("Reset Tournament", type="secondary"):
        st.session_state.players, st.session_state.history, st.session_state.current_round, st.session_state.current_pods = [], [], 0, []
        st.rerun()

# --- MAIN UI ---
tab1, tab2, tab3 = st.tabs(["📊 Standings", "⚔️ Active Pods", "📜 History"])

with tab1:
    st.header("🏆 Leaderboard")
    df = get_commander_standings()
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Add players and start a round!")

with tab2:
    if st.session_state.current_round == 0:
        if st.button("🚀 Start Round 1", type="primary"):
            generate_commander_pods(); st.rerun()
    elif st.session_state.current_pods:
        st.header(f"⚔️ Round {st.session_state.current_round}")
        results = []
        ready = True
        
        for i, pod in enumerate(st.session_state.current_pods):
            with st.expander(f"Pod {i+1} ({len(pod)} players)", expanded=True):
                if st.session_state.mode == "Casual":
                    win = st.selectbox("Winner?", ["Select..."] + pod, key=f"w_{i}")
                    if win == "Select...": ready = False
                    else: results.append({'players': pod, 'winner': win, 'type': 'Casual'})
                else:
                    # NEW: Updated Table Kill and Point Preview
                    tk = st.checkbox("Table Kill? (Winner 1st, others 4th)", key=f"tk_{i}")
                    p_ranks = {}
                    pts_map = {1: 5, 2: 3, 3: 2, 4: 1}
                    
                    if tk:
                        tw = st.selectbox("Winner?", pod, key=f"tw_{i}")
                        for p in pod: 
                            p_ranks[p] = 1 if p == tw else 4 
                    else:
                        # Manual Ranking
                        cols = st.columns(len(pod))
                        for j, p in enumerate(pod):
                            p_ranks[p] = cols[j].number_input(
                                f"{p}", 1, 4, step=1, key=f"r_{p}_{i}"
                            )
                    
                    # --- QUALITY OF LIFE: POINT PREVIEW ---
                    pod_points = [pts_map.get(rank, 1) for rank in p_ranks.values()]
                    total_p = sum(pod_points)
                    num_winners = list(p_ranks.values()).count(1)
                    
                    c1, c2 = st.columns([1, 1])
                    c1.metric("Pod Total Points", f"{total_p} pts")
                    
                    if num_winners > 1:
                        st.warning(f"⚠️ Note: {num_winners} players are marked as 1st Place.")
                    
                    results.append({'players': pod, 'ranks': p_ranks, 'type': 'Competitive'})
    else:
        st.success(f"Round {st.session_state.current_round} Complete.")
        if st.button("➡️ Generate Next Round", type="primary"):
            generate_commander_pods(); st.rerun()

with tab3:
    st.header("📜 History")
    if st.session_state.history:
        if st.button("⚠️ Undo Last Round"):
            st.session_state.history.pop(); st.session_state.current_round -= 1; st.rerun()
        for idx, rnd in enumerate(st.session_state.history):
            with st.expander(f"Round {idx+1}"):
                for pod in rnd:
                    if pod.get('type') == 'Casual':
                        st.write(f"Winner: **{pod['winner']}**")
                    else:
                        st.write(f"Ranks: {pod['ranks']}")