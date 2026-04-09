import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

st.markdown("""
    <style>
    div[data-testid="stButton"] button:has(div:contains("End Tournament")) {
        background-color: #ff4b4b;
        color: white;
        border: none;
    }
    div[data-testid="stButton"] button:has(div:contains("End Tournament")):hover {
        background-color: #ff3333;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. GLOBAL DATA LOAD (Prevents repetitive API calls) ---
@st.cache_data(ttl=600)
def get_all_data():
    events = conn.read(worksheet="Events")
    players = conn.read(worksheet="Players")
    history = conn.read(worksheet="MatchHistory")
    active_pods = conn.read(worksheet="CurrentPods")
    return events, players, history, active_pods

events_df, players_df, history_df, active_pods_df = get_all_data()

# --- 3. SESSION STATE ---
if 'active_event_code' not in st.session_state:
    st.session_state.active_event_code = ""
if 'registration_list' not in st.session_state:
    st.session_state.registration_list = []

user_email = st.user.get("email").lower() if st.user.get("is_logged_in") else None

# --- 4. CALLBACKS & SWISS LOGIC ---
def add_player_callback():
    new_p = st.session_state.player_input_field.strip()
    if new_p and new_p not in st.session_state.registration_list:
        st.session_state.registration_list.append(new_p)
    st.session_state.player_input_field = ""

def split_into_swiss_pods(players, history_df):
    n = len(players)
    if n < 3: return [players]
    scores = {p: 0 for p in players}
    past_matchups = set()
    if not history_df.empty:
        s_map = history_df.groupby('Player')['Points'].sum().to_dict()
        for p in scores: scores[p] = s_map.get(p, 0)
        cols = ['event_code', 'Round', 'Pod']
        if all(c in history_df.columns for c in cols):
            for _, group in history_df.groupby(cols):
                m = group['Player'].tolist()
                for i in range(len(m)):
                    for j in range(i + 1, len(m)):
                        past_matchups.add(frozenset([m[i], m[j]]))

    pod_sizes = ([4] * (n // 4))
    remainder = n % 4
    if remainder == 1: pod_sizes = ([4] * (max(0, len(pod_sizes)-2))) + [3, 3, 3]
    elif remainder == 2: pod_sizes = ([4] * (max(0, len(pod_sizes)-1))) + [3, 3]
    elif remainder == 3: pod_sizes.append(3)
    
    available = sorted(players, key=lambda x: (scores[x], random.random()), reverse=True)
    pods = []
    for size in pod_sizes:
        current_pod = []
        anchor = available.pop(0)
        current_pod.append(anchor)
        for _ in range(size - 1):
            best_idx = 0
            for idx, cand in enumerate(available):
                if not any(frozenset([cand, p]) in past_matchups for p in current_pod) or idx > 3:
                    best_idx = idx
                    break
            current_pod.append(available.pop(best_idx))
        pods.append(current_pod)
    return pods

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title("Settings")
    if not st.user.get("is_logged_in"):
        if st.button("Admin Login"): st.login()
    else:
        st.write(f"Logged in: **{st.user.get('name')}**")
        if st.button("Log Out"): st.logout()
    st.divider()

    if not st.session_state.active_event_code:
        input_code = st.text_input("Enter Event Code:").upper().strip()
        if st.button("Load Event"):
            if input_code in events_df['event_code'].values:
                st.session_state.active_event_code = input_code
                st.rerun()
            else: st.error("Invalid Code")
    else:
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (user_email == event_row['admin_email'].lower()) if user_email else False
        st.subheader(f"Code: {st.session_state.active_event_code}")
        
        if is_admin:
            st.success("Admin Mode")
            p_df_all = players_df # local copy
            confirmed = p_df_all[p_df_all['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
            
            with st.expander("Manage Roster"):
                with st.form("add_p", clear_on_submit=True):
                    st.text_input("Player Name", key="player_input_field")
                    st.form_submit_button("Add to List", on_click=add_player_callback)
                if st.session_state.registration_list:
                    st.write("**Pending:**")
                    for p in st.session_state.registration_list: st.text(f"• {p}")
                    if st.button("Save Pending to Sheet"):
                        new_rows = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.registration_list])
                        conn.update(worksheet="Players", data=pd.concat([players_df, new_rows], ignore_index=True))
                        st.session_state.registration_list = []; st.cache_data.clear(); st.rerun()
                if confirmed:
                    drop_p = st.selectbox("Drop Player", ["-- Select --"] + confirmed)
                    if st.button("Confirm Drop") and drop_p != "-- Select --":
                        updated = players_df[~((players_df['event_code'] == st.session_state.active_event_code) & (players_df['player_name'] == drop_p))]
                        conn.update(worksheet="Players", data=updated)
                        st.cache_data.clear(); st.rerun()
            
            if st.button("Sync Data", use_container_width=True):
                st.cache_data.clear(); st.rerun()
            if st.button("End Tournament", use_container_width=True, type="primary"):
                remaining_pods = active_pods_df[active_pods_df['event_code'] != st.session_state.active_event_code]
                conn.update(worksheet="CurrentPods", data=remaining_pods)
                st.session_state.active_event_code = ""; st.cache_data.clear(); st.rerun()
        else:
            st.info("View Only Mode")
            if st.button("Exit Event"):
                st.session_state.active_event_code = ""; st.rerun()

# --- 6. MAIN UI ---
if st.session_state.active_event_code:
    this_event_history = history_df[history_df['event_code'] == st.session_state.active_event_code].copy()
    this_event_players = players_df[players_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
    this_event_pods = active_pods_df[active_pods_df['event_code'] == st.session_state.active_event_code]
    
    current_round = int(this_event_history['Round'].max() + 1) if not this_event_history.empty else 1
    
    st.title(f"🛡️ EDH Tournament: {st.session_state.active_event_code}")
    tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "⚔️ Active Pods", "📜 Match History"])
    
    with tab1:
        if not this_event_history.empty:
            this_event_history['Points'] = this_event_history['Points'].astype(int)
            lb = this_event_history.groupby('Player').agg(Points=('Points', 'sum'), Wins=('Result', lambda x: (x == 'Winner').sum())).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else: st.info("Waiting for first round results.")

    with tab2:
        if this_event_pods.empty:
            if is_admin:
                st.subheader(f"Prepare Round {current_round}")
                if st.button(f"Generate Round {current_round}", type="primary"):
                    new_pods = split_into_swiss_pods(this_event_players, this_event_history)
                    rows = []
                    for i, pod in enumerate(new_pods):
                        for p in pod: rows.append({"event_code": st.session_state.active_event_code, "Pod": i+1, "Player": p})
                    updated_pods = pd.concat([active_pods_df, pd.DataFrame(rows)], ignore_index=True)
                    conn.update(worksheet="CurrentPods", data=updated_pods)
                    st.cache_data.clear(); st.rerun()
            else: st.info(f"Waiting for Admin to publish Round {current_round}...")
        else:
            st.subheader(f"Active Pairings: Round {current_round}")
            pod_ids = sorted(this_event_pods['Pod'].unique())
            res_rows = []
            ready_to_finalize = True
            for pid in pod_ids:
                members = this_event_pods[this_event_pods['Pod'] == pid]['Player'].tolist()
                with st.expander(f"Pod {pid}: {', '.join(members)}", expanded=True):
                    if is_admin:
                        win = st.selectbox("Select Winner", ["--"] + members, key=f"p{pid}")
                        if win == "--": ready_to_finalize = False
                        else:
                            for p in members:
                                res_rows.append({"event_code": st.session_state.active_event_code, "Round": current_round, "Pod": pid, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        for p in members: st.write(f"• {p}")
            if is_admin and st.button("Finalize Round", disabled=not ready_to_finalize, type="primary"):
                conn.update(worksheet="MatchHistory", data=pd.concat([history_df, pd.DataFrame(res_rows)], ignore_index=True))
                remaining = active_pods_df[active_pods_df['event_code'] != st.session_state.active_event_code]
                conn.update(worksheet="CurrentPods", data=remaining)
                st.cache_data.clear(); st.rerun()

    with tab3:
        if not this_event_history.empty:
            for r in sorted(this_event_history['Round'].unique(), reverse=True):
                with st.expander(f"Round {int(r)}"):
                    rd = this_event_history[this_event_history['Round'] == r]
                    for p_num in sorted(rd['Pod'].unique()):
                        p_data = rd[rd['Pod'] == p_num]
                        st.markdown(f"**Pod {int(p_num)}: {', '.join(p_data['Player'].tolist())}**")
                        st.table(p_data[["Player", "Result", "Points"]])
        else: st.info("No match history recorded yet.")
