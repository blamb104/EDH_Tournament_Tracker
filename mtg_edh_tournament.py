import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# Custom CSS for the End Tournament button (Primary style + Red)
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

# --- 2. AUTHENTICATION ---
if not st.user.get("is_logged_in"):
    st.title("EDH Tournament Portal")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

user_email = st.user.get("email")

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

# --- 4. CALLBACKS & HELPERS ---
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
    while new_code in df['event_code'].values:
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

    num_3s = 0
    if n % 4 == 1: num_3s = 3
    elif n % 4 == 2: num_3s = 2
    elif n % 4 == 3: num_3s = 1
    pod_sizes = ([4] * ((n - (num_3s * 3)) // 4)) + ([3] * num_3s)

    available = sorted(players, key=lambda x: (scores[x], random.random()), reverse=True)
    pods = []
    for size in pod_sizes:
        current_pod = []
        anchor = available.pop(0)
        current_pod.append(anchor)
        for _ in range(size - 1):
            best_match_idx = 0
            for idx, candidate in enumerate(available):
                already_played = any(frozenset([candidate, p]) in past_matchups for p in current_pod)
                if not already_played or idx > 3: 
                    best_match_idx = idx
                    break
            current_pod.append(available.pop(best_match_idx))
        pods.append(current_pod)
    return pods

# --- 5. DATA SYNC ---
if st.session_state.active_event_code:
    hist_df = load_sheet("MatchHistory", force_refresh=False)
    event_history = hist_df[hist_df['event_code'] == st.session_state.active_event_code].copy()
    if not event_history.empty:
        event_history['Points'] = event_history['Points'].astype(int)
        if not st.session_state.current_pods:
            st.session_state.current_round = int(event_history['Round'].max()) + 1
    elif event_history.empty and not st.session_state.current_pods:
        st.session_state.current_round = 1
else:
    event_history = pd.DataFrame()

# --- 6. SIDEBAR ---
with st.sidebar:
    cols = st.columns([1, 4])
    cols[0].image(st.user.get("picture", "https://cdn-icons-png.flaticon.com/512/149/149071.png"), width=40)
    cols[1].write(f"**{st.user.get('name', 'User')}**")
    if st.button("Log Out"): st.logout()
    st.divider()

    auth_df = load_sheet("AuthorizedAdmins")
    authorized_emails = auth_df['email'].str.lower().tolist() if not auth_df.empty else []
    is_authorized = user_email.lower() in authorized_emails

    if not st.session_state.active_event_code:
        if is_authorized and st.button("Create New Event", use_container_width=True, type="primary"):
            st.session_state.active_event_code = create_event(user_email)
            st.session_state.current_round = 1
            st.rerun()
        input_code = st.text_input("Enter Event Code:").upper().strip()
        if input_code:
            events_df = load_sheet("Events")
            if input_code in events_df['event_code'].values:
                st.session_state.active_event_code = input_code
                st.rerun()
    else:
        st.subheader(f"Event: {st.session_state.active_event_code}")
        events_df = load_sheet("Events")
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (event_row['admin_email'] == user_email)
        has_started = not event_history.empty or len(st.session_state.current_pods) > 0
        
        if not has_started:
            with st.expander("Scoring Rules Guide", expanded=True):
                st.markdown("Casual: 3 pts Winner / 1 pt Player\n\nCompetitive: Manual Entry (0-10)")
                if is_admin:
                    st.session_state.scoring_mode = st.radio("Select System:", ["Casual", "Competitive"])
        else:
            st.info(f"Mode: {st.session_state.scoring_mode}")

        if is_admin:
            with st.expander("Manage Roster", expanded=not has_started):
                if not has_started:
                    with st.form("player_entry_form", clear_on_submit=True):
                        st.text_input("Enter Player Name", key="player_input_field")
                        st.form_submit_button("Register Player", on_click=add_player_callback)
                    
                    # Show the temporary list here
                    if st.session_state.registration_list:
                        st.write("**Pending Registration:**")
                        for p in st.session_state.registration_list:
                            st.text(f"• {p}")
                        
                        if st.button("Confirm Roster", type="primary"):
                            p_df = load_sheet("Players", force_refresh=True)
                            new_rows = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.registration_list])
                            conn.update(worksheet="Players", data=pd.concat([p_df, new_rows], ignore_index=True))
                            st.session_state.registration_list = []
                            st.cache_data.clear(); st.rerun()
                else:
                    late_p = st.text_input("Add Late Player")
                    if st.button("Add Late"):
                        p_df = load_sheet("Players", force_refresh=True)
                        conn.update(worksheet="Players", data=pd.concat([p_df, pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": late_p}])], ignore_index=True))
                        st.cache_data.clear(); st.rerun()
                
                p_df = load_sheet("Players")
                clist = p_df[p_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
                if clist:
                    drop_p = st.selectbox("Drop Player", ["-- Select --"] + clist)
                    if st.button("Confirm Drop") and drop_p != "-- Select --":
                        p_df = load_sheet("Players", force_refresh=True)
                        updated = p_df[~((p_df['event_code'] == st.session_state.active_event_code) & (p_df['player_name'] == drop_p))]
                        conn.update(worksheet="Players", data=updated)
                        st.cache_data.clear(); st.rerun()

        if st.button("Sync Data", use_container_width=True, type="secondary"):
            st.cache_data.clear(); st.rerun()
        
        if is_admin and st.button("End Tournament", use_container_width=True, type="primary"):
            st.session_state.active_event_code = ""; st.session_state.current_pods = []; st.session_state.current_round = 1; st.cache_data.clear(); st.rerun()

# --- 7. MAIN UI ---
if st.session_state.active_event_code:
    st.title(f"🛡️ EDH Tournament: {st.session_state.active_event_code}")
    tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "⚔️ Active Pods", "📜 Match History"])
    
    with tab1:
        if not event_history.empty:
            lb = event_history.groupby('Player').agg(Points=('Points', 'sum'), Wins=('Result', lambda x: (x == 'Winner').sum())).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else: st.info("Waiting for results.")
    
    with tab2:
        p_df = load_sheet("Players")
        confirmed = p_df[p_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
        if not st.session_state.current_pods:
            st.subheader(f"Prepare Round {st.session_state.current_round}")
            if is_admin:
                if len(confirmed) >= 3:
                    if st.button(f"Generate Round {st.session_state.current_round}", type="primary"):
                        st.session_state.current_pods = split_into_swiss_pods(confirmed, event_history)
                        st.rerun()
                else: st.warning("Need 3+ players.")
        else:
            st.subheader(f"Reporting Round {st.session_state.current_round}")
            results_data = []
            all_reported = True
            for i, pod in enumerate(st.session_state.current_pods):
                pod_num = i + 1
                with st.expander(f"Pod {pod_num}: {', '.join(pod)}", expanded=True):
                    if st.session_state.scoring_mode == "Casual":
                        win = st.selectbox("Winner", ["Select..."] + pod, key=f"win_{i}")
                        if win == "Select...": all_reported = False
                        else:
                            for p in pod: results_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Pod": pod_num, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        pod_points = {p: st.number_input(f"Pts {p}", 0, 10, 0, key=f"pts_{i}_{p}") for p in pod}
                        max_p = max(pod_points.values())
                        for p, pts in pod_points.items(): results_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Pod": pod_num, "Player": p, "Points": pts, "Result": "Winner" if pts == max_p and pts > 0 else "Participant"})
            if is_admin and st.button("Finalize Round", disabled=not all_reported, type="primary"):
                try:
                    hist = load_sheet("MatchHistory", force_refresh=True)
                    new_data_df = pd.DataFrame(results_data)
                    conn.update(worksheet="MatchHistory", data=pd.concat([hist, new_data_df], ignore_index=True))
                    st.cache_data.clear(); st.session_state.current_pods = []; st.session_state.current_round += 1; st.rerun()
                except Exception as e: st.error(f"Error: {e}")
    
    with tab3:
        st.header("Match History")
        if not event_history.empty:
            rounds = sorted(event_history['Round'].unique())
            for r in rounds:
                with st.expander(f"Round {int(r)}", expanded=(r == max(rounds))):
                    round_data = event_history[event_history['Round'] == r]
                    pods_in_round = sorted(round_data['Pod'].unique())
                    for p_num in pods_in_round:
                        st.markdown(f"**Pod {int(p_num)}**")
                        pod_df = round_data[round_data['Pod'] == p_num][["Player", "Result", "Points"]]
                        st.table(pod_df)
                        st.divider()
            with st.expander("View All Match Data"):
                st.dataframe(event_history.sort_values(by=["Round", "Pod"], ascending=[True, True]), use_container_width=True, hide_index=True)
        else: st.info("No matches played.")
