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

def load_sheet(name, force_refresh=False):
    ttl = 0 if force_refresh else 600
    return conn.read(worksheet=name, ttl=ttl)

# --- 2. AUTHENTICATION & ROLE CHECK ---
# Admin login is required to CREATE or MANAGE. 
# Viewers do NOT need to log in, but they won't have admin privileges.
user_email = st.user.get("email").lower() if st.user.get("is_logged_in") else None

# --- 3. SESSION STATE ---
states = {
    'current_pods': [],
    'active_event_code': "",
    'current_round': 1,
    'registration_list': [],
    'scoring_mode': "Casual"
}
for key, val in states.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 4. HELPERS ---
def add_player_callback():
    new_p = st.session_state.player_input_field.strip()
    if new_p and new_p not in st.session_state.registration_list:
        st.session_state.registration_list.append(new_p)
    st.session_state.player_input_field = ""

def generate_unique_code():
    chars = string.ascii_uppercase + string.digits
    return "EDH-" + "".join(random.choice(chars) for _ in range(6))

def create_event(admin_email):
    df = load_sheet("Events", force_refresh=True)
    new_code = generate_unique_code()
    new_event = pd.DataFrame([{"event_code": new_code, "admin_email": admin_email, "status": "Active"}])
    conn.update(worksheet="Events", data=pd.concat([df, new_event], ignore_index=True))
    return new_code

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
    if remainder == 1: pod_sizes = ([4] * (len(pod_sizes)-2)) + [3, 3, 3] if len(pod_sizes) >= 2 else [3, 3, 3]
    elif remainder == 2: pod_sizes = ([4] * (len(pod_sizes)-1)) + [3, 3] if len(pod_sizes) >= 1 else [3, 3]
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

# --- 5. DATA FETCH ---
if st.session_state.active_event_code:
    hist_df = load_sheet("MatchHistory", force_refresh=False)
    event_history = hist_df[hist_df['event_code'] == st.session_state.active_event_code].copy()
    if not event_history.empty:
        event_history['Points'] = event_history['Points'].astype(int)
        if not st.session_state.current_pods:
            st.session_state.current_round = int(event_history['Round'].max()) + 1
else:
    event_history = pd.DataFrame()

# --- 6. SIDEBAR ---
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
            events_df = load_sheet("Events")
            if input_code in events_df['event_code'].values:
                st.session_state.active_event_code = input_code
                st.rerun()
            else: st.error("Invalid Code")
        
        # Admin Only: Create Event
        auth_df = load_sheet("AuthorizedAdmins")
        if user_email in auth_df['email'].str.lower().tolist():
            if st.button("Create New Tournament", type="primary"):
                st.session_state.active_event_code = create_event(user_email)
                st.rerun()
    else:
        # Determine if current user is the Admin for THIS event
        events_df = load_sheet("Events")
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (event_row['admin_email'].lower() == user_email)

        st.subheader(f"Code: {st.session_state.active_event_code}")
        
        if is_admin:
            st.success("You are Admin")
            p_df = load_sheet("Players", force_refresh=True)
            confirmed = p_df[p_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
            
            with st.expander("Manage Players"):
                with st.form("add_p", clear_on_submit=True):
                    st.text_input("Player Name", key="player_input_field")
                    st.form_submit_button("Add", on_click=add_player_callback)
                for p in st.session_state.registration_list: st.text(f"• {p} (Pending)")
                if st.session_state.registration_list and st.button("Save Roster"):
                    new_df = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.registration_list])
                    conn.update(worksheet="Players", data=pd.concat([p_df, new_df], ignore_index=True))
                    st.session_state.registration_list = []; st.cache_data.clear(); st.rerun()
            
            if st.button("Sync Data", use_container_width=True):
                st.cache_data.clear(); st.rerun()
            if st.button("End Tournament", use_container_width=True, type="primary"):
                st.session_state.active_event_code = ""; st.session_state.current_pods = []; st.rerun()
        else:
            st.info("View Only Mode")
            if st.button("Exit Event"):
                st.session_state.active_event_code = ""; st.rerun()

# --- 7. MAIN UI ---
if st.session_state.active_event_code:
    st.title(f"🛡️ EDH Tournament: {st.session_state.active_event_code}")
    tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "⚔️ Active Pods", "📜 Match History"])
    
    with tab1:
        if not event_history.empty:
            lb = event_history.groupby('Player').agg(Points=('Points', 'sum'), Wins=('Result', lambda x: (x == 'Winner').sum())).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else: st.info("Waiting for first round results.")

    with tab2:
        p_df = load_sheet("Players")
        confirmed = p_df[p_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
        
        if not st.session_state.current_pods:
            if is_admin:
                if st.button(f"Generate Round {st.session_state.current_round}", type="primary"):
                    st.session_state.current_pods = split_into_swiss_pods(confirmed, event_history)
                    st.rerun()
            else: st.info(f"Waiting for Admin to start Round {st.session_state.current_round}...")
        else:
            res_data = []
            all_set = True
            for i, pod in enumerate(st.session_state.current_pods):
                with st.expander(f"Pod {i+1}: {', '.join(pod)}", expanded=True):
                    if is_admin:
                        win = st.selectbox("Winner", ["Select..."] + pod, key=f"w_{i}")
                        if win == "Select...": all_set = False
                        else:
                            for p in pod: res_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Pod": i+1, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        for p in pod: st.write(f"• {p}")
            
            if is_admin and st.button("Finalize Round", disabled=not all_set, type="primary"):
                h = load_sheet("MatchHistory", force_refresh=True)
                conn.update(worksheet="MatchHistory", data=pd.concat([h, pd.DataFrame(res_data)], ignore_index=True))
                st.session_state.current_pods = []; st.session_state.current_round += 1; st.cache_data.clear(); st.rerun()

    with tab3:
        if not event_history.empty:
            for r in sorted(event_history['Round'].unique(), reverse=True):
                with st.expander(f"Round {int(r)}"):
                    rd = event_history[event_history['Round'] == r]
                    for p_num in sorted(rd['Pod'].unique()):
                        st.markdown(f"**Pod {int(p_num)}**")
                        st.table(rd[rd['Pod'] == p_num][["Player", "Result", "Points"]])
        else: st.info("No history yet.")
