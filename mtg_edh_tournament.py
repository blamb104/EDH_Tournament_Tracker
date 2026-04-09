import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet(name, force_refresh=False):
    ttl = 0 if force_refresh else 600
    return conn.read(worksheet=name, ttl=ttl)

# --- 2. AUTHENTICATION ---
if not st.user.get("is_logged_in"):
    st.title("EDH Tournament Portal")
    st.info("Please log in with Google to manage or join an event.")
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
    """Swiss pairings: group by score, maximize 4-man pods, avoid 2-man pods and repeats."""
    n = len(players)
    if n < 3: return [players]
    
    # Calculate scores
    scores = {p: 0 for p in players}
    if not history_df.empty:
        s_map = history_df.groupby('Player')['Points'].sum().to_dict()
        for p in scores: scores[p] = s_map.get(p, 0)
    
    # Track past matchups
    past_matchups = set()
    if not history_df.empty:
        for (ev, rd), group in history_df.groupby(['event_code', 'Round']):
            pod_members = group['Player'].tolist()
            for i in range(len(pod_members)):
                for j in range(i + 1, len(pod_members)):
                    past_matchups.add(frozenset([pod_members[i], pod_members[j]]))

    # Determine pod sizes (Logic to avoid 2s)
    num_3s = 0
    if n % 4 == 1: num_3s = 3
    elif n % 4 == 2: num_3s = 2
    elif n % 4 == 3: num_3s = 1
    
    pod_sizes = ([4] * ((n - (num_3s * 3)) // 4)) + ([3] * num_3s)
    
    # Sort players by score (High to Low)
    available = sorted(players, key=lambda x: scores[x], reverse=True)
    pods = []

    for size in pod_sizes:
        current_pod = []
        anchor = available.pop(0) # Take highest score
        current_pod.append(anchor)
        
        for _ in range(size - 1):
            best_match_idx = 0
            # Look for someone with similar score who hasn't played with current_pod
            for idx, candidate in enumerate(available):
                if not any(frozenset([candidate, p]) in past_matchups for p in current_pod):
                    best_match_idx = idx
                    break
            current_pod.append(available.pop(best_match_idx))
        pods.append(current_pod)
    return pods

# --- 5. ROUND TRACKING ---
if st.session_state.active_event_code:
    hist_df = load_sheet("MatchHistory")
    event_history = hist_df[hist_df['event_code'] == st.session_state.active_event_code]
    if not event_history.empty and not st.session_state.current_pods:
        st.session_state.current_round = int(event_history['Round'].max()) + 1
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
        st.subheader("Tournament Hub")
        if is_authorized:
            if st.button("Create New Event", use_container_width=True):
                new_code = create_event(user_email)
                st.session_state.active_event_code = new_code
                st.rerun()
        input_code = st.text_input("Enter Event Code:").upper().strip()
        if input_code:
            events_df = load_sheet("Events")
            if input_code in events_df['event_code'].values:
                st.session_state.active_event_code = input_code
                st.rerun()
    else:
        events_df = load_sheet("Events")
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (event_row['admin_email'] == user_email)
        
        st.subheader(f"Event: {st.session_state.active_event_code}")
        has_started = not event_history.empty or len(st.session_state.current_pods) > 0
        
        if not has_started and is_admin:
            st.session_state.scoring_mode = st.radio("Scoring System", ["Casual", "Competitive"], help="Casual: 3 pts win, 1 pt play. Competitive: Manual entry.")
            st.write("### Player Entry")
            with st.form("player_entry_form", clear_on_submit=True):
                st.text_input("Enter Player Name", key="player_input_field")
                st.form_submit_button("Register Player", on_click=add_player_callback)
            
            if st.session_state.registration_list:
                st.write(f"Pending Registration: {len(st.session_state.registration_list)}")
                for p in st.session_state.registration_list: st.text(f"- {p}")
                if st.button("Confirm and Upload Roster", type="primary", use_container_width=True):
                    p_df = load_sheet("Players", force_refresh=True)
                    new_rows = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.registration_list])
                    conn.update(worksheet="Players", data=pd.concat([p_df, new_rows], ignore_index=True))
                    st.session_state.registration_list = []
                    st.rerun()

        st.divider()
        if st.button("Sync Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        if is_admin and st.button("End Tournament", type="secondary", use_container_width=True):
            st.session_state.active_event_code = ""; st.session_state.current_pods = []; st.session_state.registration_list = []; st.rerun()

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
            st.write(f"Roster: {len(confirmed)} players confirmed.")
            if is_admin:
                if len(confirmed) >= 3:
                    if st.button(f"Generate Round {st.session_state.current_round}", type="primary"):
                        st.session_state.current_pods = split_into_swiss_pods(confirmed, event_history)
                        st.rerun()
                else: st.warning("Minimum 3 players required.")
        else:
            st.subheader(f"Reporting Round {st.session_state.current_round}")
            results_data = []
            all_reported = True
            for i, pod in enumerate(st.session_state.current_pods):
                with st.expander(f"Pod {i+1}: {', '.join(pod)}", expanded=True):
                    if st.session_state.scoring_mode == "Casual":
                        win = st.selectbox("Winner", ["Select..."] + pod, key=f"win_{i}")
                        if win == "Select...": all_reported = False
                        else:
                            for p in pod: results_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        st.write("Points Entry:")
                        pod_points = {}
                        for p in pod: pod_points[p] = st.number_input(f"Points for {p}", 0, 10, 0, key=f"pts_{i}_{p}")
                        max_p = max(pod_points.values())
                        for p, pts in pod_points.items(): results_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Player": p, "Points": pts, "Result": "Winner" if pts == max_p and pts > 0 else "Participant"})

            if is_admin and st.button("Finalize and Upload Results", disabled=not all_reported):
                hist = load_sheet("MatchHistory", force_refresh=True)
                conn.update(worksheet="MatchHistory", data=pd.concat([hist, pd.DataFrame(results_data)], ignore_index=True))
                st.session_state.current_pods = []
                st.session_state.current_round += 1
                st.cache_data.clear() 
                st.rerun()

    with tab3:
        st.header("Match History")
        st.dataframe(event_history, use_container_width=True)
