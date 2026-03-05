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

@st.dialog("Review Round Results")
def confirm_results_dialog(results):
    st.write(f"### 🛡️ Round {st.session_state.current_round} Summary")
    st.write("Please verify the results for each pod before finalizing:")
    st.divider()

    for i, entry in enumerate(results):
        st.markdown(f"#### Pod {i+1}")
        
        if entry.get('type') == 'Casual':
            winner = entry['winner']
            players = entry['players']
            for p in players:
                icon = "👑 **Winner**" if p == winner else "⚔️ Participant"
                st.write(f"- {p}: {icon}")
        else:
            # Competitive: Sort by rank to show 1st place at the top
            ranks = entry['ranks']
            sorted_ranks = sorted(ranks.items(), key=lambda x: x[1])
            summary = []
            for p, r in sorted_ranks:
                medal = "🥇" if r == 1 else "🥈" if r == 2 else "🥉" if r == 3 else "💀"
                summary.append(f"{medal} **{p}** (Rank {r})")
            st.write("  \n".join(summary))
        st.divider()
    
    col1, col2 = st.columns(2)
    if col1.button("Confirm and Finalize", type="primary", use_container_width=True):
        st.session_state.history.append(results)
        st.session_state.current_pods = [] # Clears pods to trigger "Generate" view
        st.session_state.last_round_submitted = st.session_state.current_round
        st.rerun()
    
    if col2.button("Back to Editing", use_container_width=True):
        st.rerun()

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
    if st.session_state.current_round == 0:
        st.text_input(
        "Enter Player Name:", 
        key="player_input", 
        on_change=add_player_callback,
        placeholder="Type name and hit Enter...",
        autocomplete="new-password" 
        )
    else:
        # This shows once Round 1 is generated
        st.success(f"🏆 Tournament in Progress (Round {st.session_state.current_round})")
        
    if st.session_state.players:
        st.write(f"**Total Players:** {len(st.session_state.players)}") 
        with st.expander("View/Remove Players"):
            for p in st.session_state.players:
                cols = st.columns([4, 1])
                cols[0].write(p)
                if cols[1].button("❌", key=f"del_{p}"):
                    st.session_state.players.remove(p)
                    st.rerun()
    else:
        st.info("Waiting for players...")

# --- MAIN UI ---
st.title("🛡️ EDH Tournament")
tab1, tab2, tab3 = st.tabs(["🏆 Leaderboard", "⚔️ Active Pods", "📜 Match History"])

with tab1:
    st.header("🏆 Leaderboard")
    
    # Check if ANY results have been submitted yet
    if not st.session_state.history:
        st.info("Add players in the sidebar. The leaderboard will be displayed after you submit Round 1 results.")
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
    # --- PHASE 1: NO ACTIVE PODS (Generation View) ---
    if not st.session_state.current_pods:
        # Display the success message if a round was just finished
        if 'last_round_submitted' in st.session_state and st.session_state.last_round_submitted > 0:
            st.success(f"Round {st.session_state.last_round_submitted} results recorded successfully!")

        num_players = len(st.session_state.players)
        
        # Minimum player check
        if num_players < 6:
            st.header("⚔️ Prepare for Battle")
            st.warning(f"⚠️ **Minimum 6 players required.** (Current: {num_players})")
            st.info("To create balanced 3 and 4-person pods, we need at least 6 players registered in the sidebar.")
            st.button("Start Tournament", type="primary", disabled=True)
        else:
            st.header("⚔️ Prepare for Battle")
            label = "Start Tournamnet" if st.session_state.current_round == 0 else f"➡️ Generate Round {st.session_state.current_round + 1}"
            
            if st.button(label, type="primary", use_container_width=True):
                # Reset the success notification for the new round
                st.session_state.last_round_submitted = 0 
                st.toast("Calculating pairings to minimize rematches...", icon="⚔️")
                generate_commander_pods()
                st.rerun()
                
    # --- PHASE 2: ACTIVE PODS (Score Reporting View) ---
    else:
        st.header(f"⚔️ Round {st.session_state.current_round}")
        st.info("Enter the results for each pod below.")
        
        results_to_submit = []
        all_pods_filled = True 
        
        # Loop through each pod generated by generate_commander_pods()
        for i, pod in enumerate(st.session_state.current_pods):
            player_names = ", ".join(pod)
            
            with st.expander(f"Pod {i+1}: {player_names}", expanded=True):
                # --- CASUAL SCORING ---
                if st.session_state.mode == "Casual":
                    win = st.selectbox(
                        "Who won this game?", 
                        ["Select..."] + pod, 
                        key=f"w_{st.session_state.current_round}_{i}"
                    )
                    
                    if win == "Select...":
                        all_pods_filled = False
                        st.caption("Waiting for a winner...")
                    else:
                        st.success(f"Winner: {win}")
                    
                    results_to_submit.append({'players': pod, 'winner': win, 'type': 'Casual'})
                
                # --- COMPETITIVE SCORING ---
                else:
                    tk = st.checkbox("Table Kill? (Winner takes 1st, everyone else takes 4th)", key=f"tk_{i}")
                    p_ranks = {}
                    pts_map = {1: 5, 2: 3, 3: 2, 4: 1}
                    
                    if tk:
                        tw = st.selectbox("Winner?", pod, key=f"tw_{i}")
                        for p in pod: 
                            p_ranks[p] = 1 if p == tw else 4 
                    else:
                        st.write("Assign Ranks (1-4):")
                        cols = st.columns(len(pod))
                        for j, p in enumerate(pod):
                            p_ranks[p] = cols[j].number_input(f"{p}", 1, 4, step=1, key=f"r_{p}_{i}")
                    
                    # Point Preview Metric
                    pod_points = [pts_map.get(rank, 1) for rank in p_ranks.values()]
                    num_winners = list(p_ranks.values()).count(1)
                    
                    m1, m2 = st.columns(2)
                    m1.metric("Total Pod Points", f"{sum(pod_points)} pts")
                    if num_winners > 1:
                        m2.warning(f"Multiple winners ({num_winners}) detected.")
                    
                    results_to_submit.append({'players': pod, 'ranks': p_ranks, 'type': 'Competitive'})

        st.divider()
        
        # Bottom Actions
        col_sub, col_can = st.columns([3, 1])
        
        if col_sub.button("✅ Submit Round Results", type="primary", disabled=not all_pods_filled, use_container_width=True):
            confirm_results_dialog(results_to_submit)
            

with tab3:
    st.header("📜 Match History")
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
            label="📥 Download Match History (CSV)",
            data=csv_history,
            file_name=f"EDH_Tournament_History.csv",
            mime='text/csv',
            use_container_width=True
        )

    else:
        st.info("No matches played yet. Results will appear here once submitted.")




