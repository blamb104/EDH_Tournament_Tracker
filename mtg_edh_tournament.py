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

def split_into_pods(players):
    """Logic to ensure only 3 or 4 person pods, maximizing 4s."""
    n = len(players)
    if n < 3: return [players] # Not enough for a legal pod
    
    pods = []
    # Calculate number of 3-person pods needed to avoid remainders of 1 or 2
    num_3s = 0
    if n % 4 == 1: num_3s = 3 # e.g., 9 players = 3, 3, 3
    elif n % 4 == 2: num_3s = 2 # e.g., 14 players = 4, 4, 3, 3
    elif n % 4 == 3: num_3s = 1 # e.g., 7 players = 4, 3
    
    # Check if we have enough players to support the required 3-person pods
    if n < (num_3s * 3):
        # Fallback for very small groups (like 5 or 6)
        # 5 -> 3, 2 (unavoidable) | 6 -> 3, 3
        num_3s = n // 3
        
    temp_players = players.copy()
    random.shuffle(temp_players)
    
    # Extract 3-person pods first
    for _ in range(num_3s):
        if len(temp_players) >= 3:
            pods.append([temp_players.pop() for _ in range(3)])
            
    # Fill remaining players into 4-person pods
    while len(temp_players) >= 4:
        pods.append([temp_players.pop() for _ in range(4)])
        
    # Any leftovers (should only happen if n < 3)
    if temp_players:
        if pods: pods[-1].extend(temp_players)
        else: pods.append(temp_players)
        
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
            st.session_state.scoring_mode = st.radio("Scoring System", ["Casual", "Competitive"], help="Casual: 3/1 split. Competitive: Manual entry.")
            st.write("### Player Entry")
            with st.form("player_entry_form", clear_on_submit=True):
                st.text_input("Enter Player Name", key="player_input_field")
                st.form_submit_button("Register Player", on_click=add_player_callback)
            
            if st.session_state.registration_list:
                st.write(f"**Pending Registration ({len(st.session_state.registration_list)})**")
                for p in st.session_state.registration_list: st.text(f"📝 {p}")
                if st.button("Confirm & Upload Roster", type="primary", use_container_width=True):
                    p_df = load_sheet("Players", force_refresh=True)
                    new_rows = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.registration_list])
                    conn.update(worksheet="Players", data=pd.concat([p_df, new_rows], ignore_index=True))
                    st.session_state.registration_list = []
                    st.rerun()

        st.divider()
        if st.button("Refresh / Sync Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        if is_admin and st.button("End Tournament", type="secondary", use_container_width=True):
            st.session_state.active_event_code = ""; st.session_state.current_pods = []; st.session_state.registration_list = []; st.rerun()

# --- 7. MAIN UI ---
if st.session_state.active_event_code:
    st.title(f"Tournament: {st.session_state.active_event_code}")
    tab1, tab2, tab3 = st.tabs(["Leaderboard", "Active Pods", "Match History"])

    with tab1:
        if not event_history.empty:
            lb = event_history.groupby('Player').agg(Points=('Points', 'sum'), Wins=('Result', lambda x: (x == 'Winner').sum())).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else: st.info("Waiting for Round 1 results...")

    with tab2:
        p_df = load_sheet("Players")
        confirmed_players = p_df[p_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()

        if not st.session_state.current_pods:
            st.subheader(f"Prepare Round {st.session_state.current_round}")
            st.write(f"Confirmed Roster: **{len(confirmed_players)} players**")
            if is_admin:
                if len(confirmed_players) >= 3:
                    if st.button(f"Generate Pairings for Round {st.session_state.current_round}", type="primary"):
                        st.session_state.current_pods = split_into_pods(confirmed_players)
                        st.rerun()
                else: st.warning("Need at least 3 players.")
        else:
            st.subheader(f"Reporting Round {st.session_state.current_round}")
            results_data = []
            all_reported = True
            for i, pod in enumerate(st.session_state.current_pods):
                pod_label = f"Pod {i+1} ({len(pod)} players): {', '.join(pod)}"
                with st.expander(pod_label, expanded=True):
                    if st.session_state.scoring_mode == "Casual":
                        win = st.selectbox("Winner", ["Select..."] + pod, key=f"win_{i}")
                        if win == "Select...": all_reported = False
                        else:
                            for p in pod: results_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        st.write("Manual Points Entry:")
                        pod_points = {}
                        for p in pod: pod_points[p] = st.number_input(f"Points for {p}", 0, 10, 0, key=f"pts_{i}_{p}")
                        max_p = max(pod_points.values())
                        for p, pts in pod_points.items(): results_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Player": p, "Points": pts, "Result": "Winner" if pts == max_p and pts > 0 else "Participant"})

            if is_admin and st.button("Finalize Round & Upload Results", disabled=not all_reported):
                hist = load_sheet("MatchHistory", force_refresh=True)
                conn.update(worksheet="MatchHistory", data=pd.concat([hist, pd.DataFrame(results_data)], ignore_index=True))
                st.session_state.current_pods = []
                st.session_state.current_round += 1
                st.cache_data.clear() 
                st.rerun()

    with tab3:
        st.header("Match History")
        st.dataframe(event_history, use_container_width=True)
