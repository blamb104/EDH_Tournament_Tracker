import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", page_icon="🛡️", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# Custom CSS for Buttons and UI
st.markdown("""
    <style>
    /* End Tournament Button styling */
    div[data-testid="stButton"] button:has(div:contains("End Tournament")) {
        background-color: #ff4b4b;
        color: white;
        border: none;
    }
    /* Main Landing Header styling */
    .landing-header {
        font-size: 3rem !important;
        font-weight: 800;
        text-align: center;
        margin-bottom: 0px;
    }
    .landing-subtitle {
        font-size: 1.2rem;
        text-align: center;
        color: #888;
        margin-bottom: 30px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. GLOBAL DATA LOAD ---
@st.cache_data(ttl=600)
def get_all_data():
    events = conn.read(worksheet="Events")
    players = conn.read(worksheet="Players")
    history = conn.read(worksheet="MatchHistory")
    active_pods = conn.read(worksheet="CurrentPods")
    auth_admins = conn.read(worksheet="AuthorizedAdmins")
    
    if not history.empty:
        history['Round'] = history['Round'].fillna(0).astype(int)
        history['Pod'] = history['Pod'].fillna(0).astype(int)
        history['Points'] = history['Points'].fillna(0).astype(int)
    if not active_pods.empty:
        active_pods['Pod'] = active_pods['Pod'].fillna(0).astype(int)
        
    return events, players, history, active_pods, auth_admins

events_df, players_df, history_df, active_pods_df, auth_df = get_all_data()

# --- 3. URL & REDIRECT LOGIC ---
query_params = st.query_params
if "event" in query_params and "active_event_code" not in st.session_state:
    st.session_state.active_event_code = query_params["event"]

if "active_event_code" in st.session_state and st.session_state.active_event_code:
    active_list = events_df[events_df['status'] == 'Active']['event_code'].values
    if st.session_state.active_event_code not in active_list:
        st.session_state.active_event_code = ""
        st.query_params.clear()
        st.cache_data.clear()
        st.rerun()

# --- 4. SESSION STATE DEFAULTS ---
if 'active_event_code' not in st.session_state: st.session_state.active_event_code = ""
if 'registration_list' not in st.session_state: st.session_state.registration_list = []

user_email = st.user.get("email").lower() if st.user.get("is_logged_in") else None

# --- 5. HELPERS ---
def generate_unique_code():
    chars = string.ascii_uppercase + string.digits
    return "EDH-" + "".join(random.choice(chars) for _ in range(6))

def create_event(admin_email):
    ev_refresh = conn.read(worksheet="Events", ttl=0)
    new_code = generate_unique_code()
    while new_code in ev_refresh['event_code'].values:
        new_code = generate_unique_code()
    new_event = pd.DataFrame([{"event_code": new_code, "admin_email": admin_email, "status": "Active"}])
    conn.update(worksheet="Events", data=pd.concat([ev_refresh, new_event], ignore_index=True))
    return new_code

def split_into_swiss_pods(players, history_df):
    n = len(players)
    if n < 3: return [players]
    scores = {p: 0 for p in players}
    past_matchups = set()
    if not history_df.empty:
        s_map = history_df.groupby('Player')['Points'].sum().to_dict()
        for p in scores: scores[p] = s_map.get(p, 0)
        for _, group in history_df.groupby(['event_code', 'Round', 'Pod']):
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

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title("Settings")
    if st.user.get("is_logged_in"):
        user_img = st.user.get("picture", "https://cdn-icons-png.flaticon.com/512/149/149071.png")
        cols = st.columns([1, 3])
        cols[0].image(user_img, width=40)
        cols[1].write(f"**{st.user.get('name')}**")
        if st.button("Log Out"): st.logout()
    else:
        if st.button("Admin Login"): st.login()
    
    st.divider()

    is_master_admin = user_email in auth_df['email'].str.lower().tolist() if user_email else False

    if not st.session_state.active_event_code:
        input_code = st.text_input("Event Code Login:", placeholder="e.g. EDH-XJ49").upper().strip()
        if st.button("Join Tournament", use_container_width=True):
            active_list = events_df[events_df['status'] == 'Active']['event_code'].values
            if input_code in active_list:
                st.session_state.active_event_code = input_code
                st.query_params.event = input_code
                st.rerun()
            else: st.error("Event not found or inactive.")
        
        if is_master_admin:
            st.write("---")
            if st.button("Create New Tournament", use_container_width=True, type="primary"):
                st.session_state.active_event_code = create_event(user_email)
                st.query_params.event = st.session_state.active_event_code
                st.cache_data.clear()
                st.rerun()
    else:
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_event_admin = (user_email == event_row['admin_email'].lower()) if user_email else False
        st.subheader(f"Code: {st.session_state.active_event_code}")
        
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear(); st.rerun()

        if is_event_admin:
            st.success("Admin Access")
            with st.expander("Manage Roster"):
                with st.form("add_player", clear_on_submit=True):
                    name_in = st.text_input("Player Name")
                    if st.form_submit_button("Add"):
                        if name_in: st.session_state.registration_list.append(name_in.strip())
                if st.session_state.registration_list:
                    for p in st.session_state.registration_list: st.text(f"• {p}")
                    if st.button("Save to Sheet"):
                        new_reg = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.registration_list])
                        conn.update(worksheet="Players", data=pd.concat([players_df, new_reg], ignore_index=True))
                        st.session_state.registration_list = []; st.cache_data.clear(); st.rerun()
            
            if st.button("End Tournament", type="primary", use_container_width=True):
                ev_refresh = conn.read(worksheet="Events", ttl=0)
                ev_refresh.loc[ev_refresh['event_code'] == st.session_state.active_event_code, 'status'] = 'Inactive'
                conn.update(worksheet="Events", data=ev_refresh)
                remaining_pods = active_pods_df[active_pods_df['event_code'] != st.session_state.active_event_code]
                conn.update(worksheet="CurrentPods", data=remaining_pods)
                st.session_state.active_event_code = ""; st.query_params.clear(); st.cache_data.clear(); st.rerun()
        else:
            if st.button("Exit Event", use_container_width=True):
                st.session_state.active_event_code = ""; st.query_params.clear(); st.rerun()

# --- 7. MAIN UI ---
if not st.session_state.active_event_code:
    # --- LANDING PAGE ---
    st.markdown('<p class="landing-header">🛡️ EDH Tournament Tracker</p>', unsafe_allow_html=True)
    
    # Placeholder for your Logo
    # Replace the URL with your own custom logo URL (hosted on Imgur, GitHub, etc.)
    logo_url = "https://lh3.googleusercontent.com/d/1SUjz7NARD2glitJ-vwhsouepr0iJLPoZ" 
    
    left, mid, right = st.columns([1,2,1])
    with mid:
        st.image(logo_url, use_container_width=True)
        st.info("💡 **Getting Started:** Enter an Event Code in the sidebar to view current pods and standings. Admins must log in to create or manage tournaments.") 
    st.divider()
    
else:
    # --- ACTIVE TOURNAMENT UI ---
    this_history = history_df[history_df['event_code'] == st.session_state.active_event_code].copy()
    this_players = players_df[players_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
    this_pods = active_pods_df[active_pods_df['event_code'] == st.session_state.active_event_code]
    curr_round = int(this_history['Round'].max() + 1) if not this_history.empty else 1
    
    st.title(f"⚔️ {st.session_state.active_event_code}")
    tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "⚔️ Active Pods", "📜 Match History"])
    
    with tab1:
        if not this_history.empty:
            lb = this_history.groupby('Player').agg(Points=('Points', 'sum'), Wins=('Result', lambda x: (x == 'Winner').sum())).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else: st.info("Waiting for Round 1 to finalize.")

    with tab2:
        if this_pods.empty:
            if is_event_admin:
                st.subheader(f"Prepare Round {curr_round}")
                
                # Check for minimum player count (6 players)
                player_count = len(this_players)
                
                if player_count < 6:
                    st.warning(f"⚠️ **Cannot start tournament yet.** You only have {player_count} players. You need at least 6 players to generate a Swiss round.")
                    if st.button("Refresh Player List"):
                        st.cache_data.clear()
                        st.rerun()
                else:
                    st.success(f"Ready to start! {player_count} players registered.")
                    if st.button(f"Generate Round {curr_round}", use_container_width=True):
                        new_pods = split_into_swiss_pods(this_players, this_history)
                        rows = [{"event_code": st.session_state.active_event_code, "Pod": i+1, "Player": p} for i, pod in enumerate(new_pods) for p in pod]
                        conn.update(worksheet="CurrentPods", data=pd.concat([active_pods_df, pd.DataFrame(rows)], ignore_index=True))
                        st.cache_data.clear(); st.rerun()
            else: 
                st.info(f"Waiting for Admin to post Round {curr_round}...")
        else:
            res_rows = []; all_ready = True
            for pid in sorted(this_pods['Pod'].unique()):
                members = this_pods[this_pods['Pod'] == pid]['Player'].tolist()
                with st.expander(f"Pod {int(pid)}: {', '.join(members)}", expanded=True):
                    if is_event_admin:
                        win = st.selectbox("Winner", ["--"] + members, key=f"p{pid}")
                        if win == "--": all_ready = False
                        else:
                            for p in members: res_rows.append({"event_code": st.session_state.active_event_code, "Round": curr_round, "Pod": pid, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        for p in members: st.write(f"• {p}")
            if is_event_admin and st.button("Finalize Round", disabled=not all_ready, type="primary"):
                conn.update(worksheet="MatchHistory", data=pd.concat([history_df, pd.DataFrame(res_rows)], ignore_index=True))
                remaining = active_pods_df[active_pods_df['event_code'] != st.session_state.active_event_code]
                conn.update(worksheet="CurrentPods", data=remaining)
                st.cache_data.clear(); st.rerun()

    with tab3:
        if not this_history.empty:
            for r in sorted(this_history['Round'].unique(), reverse=True):
                with st.expander(f"Round {int(r)}"):
                    rd = this_history[this_history['Round'] == r]
                    for p_num in sorted(rd['Pod'].unique()):
                        p_data = rd[rd['Pod'] == p_num]
                        st.markdown(f"**Pod {int(p_num)}: {', '.join(p_data['Player'].tolist())}**")
                        st.table(p_data[["Player", "Result", "Points"]])
