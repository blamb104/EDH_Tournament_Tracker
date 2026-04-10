import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", page_icon="🛡️", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# Custom CSS for UI Polish
st.markdown("""
    <style>
    /* End Tournament Button styling */
    div[data-testid="stButton"] button:has(div:contains("End Tournament")) {
        background-color: #ff4b4b; color: white; border: none;
    }
    /* Ghost Button for Roster 'X' */
    .stButton > button[kind="tertiary"] {
        border: none !important; background-color: transparent !important;
        padding: 0 !important; color: #ff4b4b !important; line-height: 1.5 !important;
    }
    /* Landing Header styling */
    .landing-header {
        font-size: 3rem !important; font-weight: 900; text-align: center;
        color: #FFFFFF; text-shadow: 0px 0px 20px rgba(255,255,255,0.5);
        line-height: 1; margin-bottom: 0px; white-space: nowrap;
    }
    .landing-subtitle {
        font-size: 2rem; text-align: center; color: #AAAAAA; margin-top: -10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. GLOBAL DATA LOAD (10-min TTL) ---
@st.cache_data(ttl=600)
def get_all_data():
    events = conn.read(worksheet="Events")
    players = conn.read(worksheet="Players")
    history = conn.read(worksheet="MatchHistory")
    active_pods = conn.read(worksheet="CurrentPods")
    auth_admins = conn.read(worksheet="AuthorizedAdmins")
    
    # Clean up types for consistency
    if not history.empty:
        for col in ['Round', 'Pod', 'Points']:
            history[col] = history[col].fillna(0).astype(int)
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

# --- 4. SESSION STATE & DIALOGS ---
if 'active_event_code' not in st.session_state: st.session_state.active_event_code = ""
if 'registration_list' not in st.session_state: st.session_state.registration_list = []
user_email = st.user.get("email").lower() if st.user.get("is_logged_in") else None

@st.dialog("Confirm Player Removal")
def confirm_drop(player_name):
    st.warning(f"Are you sure you want to drop **{player_name}**? This cannot be undone.")
    if st.button(f"Yes, Remove {player_name}", type="primary", use_container_width=True):
        updated = players_df[~((players_df['event_code'] == st.session_state.active_event_code) & 
                               (players_df['player_name'] == player_name))]
        conn.update(worksheet="Players", data=updated)
        st.cache_data.clear(); st.rerun()

# --- 5. HELPERS ---
def create_event(admin_email, mode):
    ev_refresh = conn.read(worksheet="Events", ttl=0)
    new_code = "EDH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_event = pd.DataFrame([{"event_code": new_code, "admin_email": admin_email, "status": "Active", "mode": mode}])
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
    rem = n % 4
    if rem == 1: pod_sizes = ([4] * (max(0, len(pod_sizes)-2))) + [3, 3, 3]
    elif rem == 2: pod_sizes = ([4] * (max(0, len(pod_sizes)-1))) + [3, 3]
    elif rem == 3: pod_sizes.append(3)
    
    available = sorted(players, key=lambda x: (scores[x], random.random()), reverse=True)
    pods = []
    for size in pod_sizes:
        current_pod = []
        anchor = available.pop(0); current_pod.append(anchor)
        for _ in range(size - 1):
            best_idx = 0
            for idx, cand in enumerate(available):
                if not any(frozenset([cand, p]) in past_matchups for p in current_pod) or idx > 3:
                    best_idx = idx; break
            current_pod.append(available.pop(best_idx))
        pods.append(current_pod)
    return pods

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title("Event Settings")
    if st.user.get("is_logged_in"):
        cols = st.columns([1, 3])
        cols[0].image(st.user.get("picture", "https://cdn-icons-png.flaticon.com/512/149/149071.png"), width=40)
        cols[1].write(f"**{st.user.get('name')}**")
        if st.button("Log Out"): st.logout()
    else:
        if st.button("Admin Login"): st.login()
    
    st.divider()
    is_master_admin = user_email in auth_df['email'].str.lower().tolist() if user_email else False

    if not st.session_state.active_event_code:
        input_code = st.text_input("Enter Event Code:").upper().strip()
        if st.button("Join Tournament", use_container_width=True, type="primary"):
            if input_code in events_df[events_df['status'] == 'Active']['event_code'].values:
                st.session_state.active_event_code = input_code; st.query_params.event = input_code; st.rerun()
            else: st.error("Code not found or Inactive.")
        
        if is_master_admin:
            st.write("---")
            new_mode = st.radio("Tournament Mode", ["Casual", "Competitive"])
            if st.button("Create New Tournament", use_container_width=True):
                st.session_state.active_event_code = create_event(user_email, new_mode)
                st.query_params.event = st.session_state.active_event_code; st.cache_data.clear(); st.rerun()
    else:
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_event_admin = (user_email == event_row['admin_email'].lower()) if user_email else False
        st.subheader(f"Code: {st.session_state.active_event_code}")
        st.caption(f"Mode: {event_row['mode']}")
        
        if st.button("Refresh Data", use_container_width=True): st.cache_data.clear(); st.rerun()

        if is_event_admin:
            with st.expander("Manage Player Roster"):
                active_names = players_df[players_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
                for p in active_names:
                    c = st.columns([0.1, 0.75, 0.15])
                    c[0].write("👤")
                    c[1].write(p)
                    if c[2].button("✖️", key=f"d_{p}", type="tertiary"): confirm_drop(p)
                st.divider()
                with st.form("add_p", clear_on_submit=True):
                    name_in = st.text_input("New Player")
                    if st.form_submit_button("Queue"):
                        if name_in and name_in not in active_names: st.session_state.registration_list.append(name_in.strip())
                if st.session_state.registration_list:
                    if st.button("Save Pending List", type="primary", use_container_width=True):
                        new_reg = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.registration_list])
                        conn.update(worksheet="Players", data=pd.concat([players_df, new_reg], ignore_index=True))
                        st.session_state.registration_list = []; st.cache_data.clear(); st.rerun()
            
            if st.button("End Tournament", type="primary", use_container_width=True):
                ev_refresh = conn.read(worksheet="Events", ttl=0)
                ev_refresh.loc[ev_refresh['event_code'] == st.session_state.active_event_code, 'status'] = 'Inactive'
                conn.update(worksheet="Events", data=ev_refresh)
                conn.update(worksheet="CurrentPods", data=active_pods_df[active_pods_df['event_code'] != st.session_state.active_event_code])
                st.session_state.active_event_code = ""; st.query_params.clear(); st.cache_data.clear(); st.rerun()
        else:
            if st.button("Exit Event", use_container_width=True): st.session_state.active_event_code = ""; st.query_params.clear(); st.rerun()

# --- 7. MAIN UI ---
if not st.session_state.active_event_code:
    st.markdown('<p class="landing-header">🛡️ EDH Tournament Tracker 🛡️</p>', unsafe_allow_html=True)
    logo_url = "https://lh3.googleusercontent.com/d/1SUjz7NARD2glitJ-vwhsouepr0iJLPoZ" # UPDATE THIS URL
    l, m, r = st.columns([1,2,1]); m.image(logo_url, use_container_width=True)
    st.divider()
else:
    this_history = history_df[history_df['event_code'] == st.session_state.active_event_code].copy()
    this_players = players_df[players_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
    this_pods = active_pods_df[active_pods_df['event_code'] == st.session_state.active_event_code]
    curr_round = int(this_history['Round'].max() + 1) if not this_history.empty else 1
    event_mode = events_df[events_df['event_code'] == st.session_state.active_event_code]['mode'].values[0]

    st.title(f"⚔️ {st.session_state.active_event_code} ({event_mode})")
    tab1, tab2, tab3 = st.tabs(["🏆 Leaderboard", "⚔️ Active Pods", "📜 History"])
    
    with tab1:
        if not this_history.empty:
            lb = this_history.groupby('Player').agg(Points=('Points', 'sum'), Wins=('Result', lambda x: (x == 'Winner').sum())).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else: st.info("Waiting for Round 1 results.")

    with tab2:
        if this_pods.empty:
            if is_event_admin:
                if len(this_players) < 6: st.warning(f"⚠️ Need 6 players (You have {len(this_players)})")
                elif st.button(f"Generate Round {curr_round}", type="primary"):
                    new_pods = split_into_swiss_pods(this_players, this_history)
                    rows = [{"event_code": st.session_state.active_event_code, "Pod": i+1, "Player": p} for i, pod in enumerate(new_pods) for p in pod]
                    conn.update(worksheet="CurrentPods", data=pd.concat([active_pods_df, pd.DataFrame(rows)], ignore_index=True))
                    st.cache_data.clear(); st.rerun()
            else: st.info(f"Waiting for Round {curr_round} pairings...")
        else:
            res_rows = []; all_ready = True
            for pid in sorted(this_pods['Pod'].unique()):
                mems = this_pods[this_pods['Pod'] == pid]['Player'].tolist()
                with st.expander(f"Pod {int(pid)}: {', '.join(mems)}", expanded=True):
                    if is_event_admin:
                        if event_mode == "Competitive":
                            cols = st.columns(len(mems))
                            for i, p in enumerate(mems):
                                pts = cols[i].number_input(f"{p}", min_value=0, max_value=10, value=1, key=f"pts_{pid}_{p}")
                                res_rows.append({"event_code": st.session_state.active_event_code, "Round": curr_round, "Pod": pid, "Player": p, "Points": pts, "Result": "Winner" if pts >= 3 else "Participant"})
                        else:
                            win = st.selectbox("Winner", ["--"] + mems, key=f"p{pid}")
                            if win == "--": all_ready = False
                            else:
                                for p in mems:
                                    res_rows.append({"event_code": st.session_state.active_event_code, "Round": curr_round, "Pod": pid, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        for p in mems: st.write(f"• {p}")
            if is_event_admin and st.button("Finalize Round", disabled=not all_ready, type="primary", use_container_width=True):
                conn.update(worksheet="MatchHistory", data=pd.concat([history_df, pd.DataFrame(res_rows)], ignore_index=True))
                conn.update(worksheet="CurrentPods", data=active_pods_df[active_pods_df['event_code'] != st.session_state.active_event_code])
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
