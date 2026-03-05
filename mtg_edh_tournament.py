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
                    rank = entry['ranks'].get(p, 4)
                    pts_map = {1: 5, 2: 3, 3: 2, 4: 1}
                    stats[p]['Points'] += pts_map.get(rank, 1)
                    if rank == 1:
                        stats[p]['Wins'] += 1
                
                # Track opponents for tiebreakers
                others = [o for o in players_in_pod if o != p]
                stats[p]['Opponents'].extend(others)

    leaderboard = []
    for p, s in stats.items():
        # Strength of Schedule: Sum of all points opponents have earned
        omp = sum(stats[o]['Points'] for o in s['Opponents'] if o in stats)
        leaderboard.append({
            'Player': p, 
            'Points': s['Points'], 
            'Wins': s['Wins'], 
            'OMP': omp
        })
    
    df = pd.DataFrame(leaderboard)
    if not df.empty:
        return df.sort_values(by=['Points', 'Wins', 'OMP'], ascending=False)
    return df

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
    st.title("Tournament Setup")
    st.session_state.mode = st.radio("Tournament Mode", ["Casual", "Competitive"])
    # --- INFO DROPDOWN ---
    with st.expander("Scoring Rules"):
        if st.session_state.mode == "Casual":
            st.markdown("""
            **Casual Scoring:**
            - **Winner:** 4 Points
            - **Others:** 1 Point
            """)
        else:
            st.markdown("""
            **Competitive Scoring:**
            - **1st Place:** 5 Points
            - **2nd Place:** 3 Points
            - **3rd Place:** 2 Points
            - **4th Place:** 1 Point
            
            **Table Kill:**
            Winner gets 1st (5pts), 
            all others get last (1pt).
            """)
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
        with st.expander("View/Remove Players"):
                for p in st.session_state.players:
                    cols = st.columns([4, 1])
                    cols[0].write(p)
                    if cols[1].button("❌", key=f"del_{p}"):
                        st.session_state.players.remove(p)
                        st.rerun()

# --- MAIN UI ---
st.title("🛡️ EDH Tournament")
tab1, tab2, tab3 = st.tabs(["📊 Standings", "⚔️ Active Pods", "📜 History"])

with tab1:
    st.header("🏆 Leaderboard")
    
    # Check if ANY results have been submitted yet
    if not st.session_state.history:
        st.info("The battlefield is empty! Add players in the sidebar and finalize Round 1 to see the leaderboard.")
    else:
        df = get_commander_standings()
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # --- EXPORT TO CSV ---
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Export Standings to CSV",
            data=csv,
            file_name=f"EDH_Tournament_Standings.csv",
            mime='text/csv',
        )

with tab2:
    if st.session_state.current_round == 0:
        # Check for minimum player count
        num_players = len(st.session_state.players)
        
        if num_players < 6:
            st.header("⚔️ Prepare for Battle")
            st.warning(f"⚠️ **Minimum 6 players required.** (Current: {num_players})")
            st.info("The pairing logic requires at least 6 players to properly distribute pods of 3 and 4.")
            
            # Show a disabled button so they know where to click later
            st.button("Start Round 1", type="primary", disabled=True, help="Add more players in the sidebar first!")
        else:
            # Requirements met - allow start
            st.success(f"Ready to go! {num_players} players registered.")
            if st.button("Start Round 1", type="primary"):
                # A quick pop-up toast for flair
                st.toast("Generating Pods...", icon="⚔️")
                generate_commander_pods()
                st.rerun()
                
    elif st.session_state.current_pods:
        st.header(f"⚔️ Round {st.session_state.current_round}")
        
        results_to_submit = []
        all_pods_filled = True  # Logic gate for the Submit button
        
        for i, pod in enumerate(st.session_state.current_pods):
            # Create a string of player names, e.g., "Alice, Bob, Charlie"
            player_names = ", ".join(pod)
            
            # Make the headers to show pod members.
            with st.expander(f"Pod {i+1}: {player_names}", expanded=True):
                if st.session_state.mode == "Casual":
                    win = st.selectbox("Winner?", ["Select..."] + pod, key=f"w_{i}")
                    if win == "Select...":
                        all_pods_filled = False
                    results_to_submit.append({'players': pod, 'winner': win, 'type': 'Casual'})
                
                else:
                    # Competitive Logic
                    tk = st.checkbox("Table Kill? (Winner 1st, others 4th)", key=f"tk_{i}")
                    p_ranks = {}
                    pts_map = {1: 5, 2: 3, 3: 2, 4: 1}
                    
                    if tk:
                        tw = st.selectbox("Winner?", pod, key=f"tw_{i}")
                        for p in pod: 
                            p_ranks[p] = 1 if p == tw else 4 
                    else:
                        cols = st.columns(len(pod))
                        for j, p in enumerate(pod):
                            p_ranks[p] = cols[j].number_input(f"{p}", 1, 4, step=1, key=f"r_{p}_{i}")
                    
                    # --- QUALITY OF LIFE: POINT PREVIEW ---
                    pod_points = [pts_map.get(rank, 1) for rank in p_ranks.values()]
                    total_p = sum(pod_points)
                    num_winners = list(p_ranks.values()).count(1)
                    
                    c1, c2 = st.columns([1, 1])
                    c1.metric("Pod Total Points", f"{total_p} pts")
                    
                    if num_winners > 1:
                        st.warning(f"⚠️ Note: {num_winners} players are marked as 1st Place.")
                    
                    results_to_submit.append({'players': pod, 'ranks': p_ranks, 'type': 'Competitive'})

        st.divider()
        
        if st.button("✅ Submit Round Results", type="primary", disabled=not all_pods_filled):
            st.session_state.history.append(results_to_submit)
            st.session_state.current_pods = [] # Clear active pods to allow next round generation
            st.success("Results recorded successfully!")
            st.rerun()

    else:
        # This shows after a round is submitted but before the next is generated
        st.success(f"Round {st.session_state.current_round} submitted.")
        if st.button("➡️ Generate Next Round", type="primary"):
            generate_commander_pods()
            st.rerun()

with tab3:
    st.header("📜 History")
    if st.session_state.history:
        # Loop forward through history (Round 1, then Round 2, etc.)
        for idx, rnd in enumerate(st.session_state.history):
            round_num = idx + 1
            with st.expander(f"Round {round_num}"):
                for pod_idx, pod in enumerate(rnd):
                    st.markdown(f"**Pod {pod_idx + 1}**")
                    
                    if pod.get('type') == 'Casual':
                        # Sort: Winner first
                        sorted_players = sorted(
                            pod['players'], 
                            key=lambda p: (p != pod['winner'], p)
                        )
                        for p in sorted_players:
                            pts = 4 if p == pod['winner'] else 1
                            icon = "👑" if p == pod['winner'] else "⚔️"
                            st.write(f"{icon} {p}: {pts} pts")
                    
                    else:
                        # Sort: 1st Place first
                        pts_map = {1: 5, 2: 3, 3: 2, 4: 1}
                        sorted_ranks = sorted(pod['ranks'].items(), key=lambda item: item[1])
                        
                        for p, rank in sorted_ranks:
                            pts = pts_map.get(rank, 1)
                            icon = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "💀"
                            st.write(f"{icon} {p}: {pts} pts (Rank: {rank})")
                    
                    st.divider()
        
        # --- CSV EXPORT LOGIC ---
        if st.session_state.history:
            st.divider()
            st.subheader("💾 Export Data")
        
        flat_history = []
        for round_idx, rnd in enumerate(st.session_state.history):
            for pod_idx, pod in enumerate(rnd):
                if pod.get('type') == 'Casual':
                    for p in pod['players']:
                        flat_history.append({
                            "Round": round_idx + 1,
                            "Pod": pod_idx + 1,
                            "Player": p,
                            "Result": "Winner" if p == pod['winner'] else "Participant",
                            "Points": 4 if p == pod['winner'] else 1
                        })
                else:
                    pts_map = {1: 5, 2: 3, 3: 2, 4: 1}
                    for p, rank in pod['ranks'].items():
                        flat_history.append({
                            "Round": round_idx + 1,
                            "Pod": pod_idx + 1,
                            "Player": p,
                            "Result": f"Rank {rank}",
                            "Points": pts_map.get(rank, 1)
                        })
        
        history_df = pd.DataFrame(flat_history)
        csv_history = history_df.to_csv(index=False).encode('utf-8')

        st.download_button(
            label="📥 Download Full Match History (CSV)",
            data=csv_history,
            file_name=f"EDH_Tournament_History_Full.csv",
            mime='text/csv',
            use_container_width=True
        )

    else:
        st.info("No history available yet.")
















