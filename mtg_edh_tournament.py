import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet(name, force_refresh=False):
    """Loads data with a 10-minute cache to prevent API Quota errors."""
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
    'draft_roster': [],
    'scoring_mode': "Casual"
}
for key, val in states.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 4. HELPER FUNCTIONS ---

def generate_unique_code():
    chars = string.ascii_uppercase + string.digits
    return "EDH-" + "".join(random.choice(chars) for _ in range(6))

def create_event(admin_email):
    df = load_sheet("Events", force_refresh=True)
    new_code = generate_unique_code()
    while new_code in df['event_code'].values:
        new_code = generate_unique_code()
    
    new_event = pd.DataFrame([{"event_code": new_code, "admin_email": admin_email, "status": "Active"}])
    updated = pd.concat([df, new_event], ignore_index=True)
    conn.update(worksheet="Events", data=updated)
    return new_code

def drop_player(event_code, name):
    df = load_sheet("Players", force_refresh=True)
    updated = df[~((df['event_code'] == event_code) & (df['player_name'] == name))]
    conn.update(worksheet="Players", data=updated)

# --- 5. DATA PERSISTENCE & ROUND TRACKING ---
if st.session_state.active_event_code:
    hist_df = load_sheet("MatchHistory")
    event_history = hist_df[hist_df['event_code'] == st.session_state.active_event_code]
    
    if not event_history.empty:
        last_recorded_round = event_history['Round'].max()
        if not st.session_state.current_pods:
            st.session_state.current_round = int(last_recorded_round) + 1
        else:
            st.session_state.current_round = int(last_recorded_round)
    else:
        st.session_state.current_round = 1
else:
    event_history = pd.DataFrame()

# --- 6. SIDEBAR ---
with st.sidebar:
    cols = st.columns([1, 4])
    cols[0].image(st.user.get("picture", "https://cdn-icons-png.flaticon.com/512/149/149071.png"), width=40)
    cols[1].write(f"**{st.user.get('name', 'User')}**")
    
    if st.button("Log Out"):
        st.logout()
    
    st.divider()

    if not st.session_state.active_event_code:
        st.subheader("Tournament Hub")
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
                st.error("Invalid Code")
    else:
        # EVENT ACTIVE MODE
        events_df = load_sheet("Events")
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (event_row['admin_email'] == user_email)

        st.subheader(f"Event: {st.session_state.active_event_code}")
        has_started = not event_history.empty or len(st.session_state.current_pods) > 0
        
        if not has_started:
            st.caption("Status: Registration Open")
            if is_admin:
                st.session_state.scoring_mode = st.radio(
                    "Scoring System", ["Casual", "Competitive"],
                    help="Casual: 3pts for Win, 1pt for Playing | Competitive: Manual Entry (5,3,2,1 default)"
                )
                with st.form("add_player_form", clear_on_submit=True):
                    new_p = st.text_input("Draft Player")
                    submitted = st.form_submit_button("Add to List")
                    if submitted and new_p:
                        if new_p not in st.session_state.draft_roster:
                            st.session_state.draft_roster.append(new_p)
                            st.rerun()
                
                if st.session_state.draft_roster:
                    st.write(f"Draft ({len(st.session_state.draft_roster)}): {', '.join(st.session_state.draft_roster)}")
                    if st.button("Clear Draft List"):
                        st.session_state.draft_roster = []
                        st.rerun()
        else:
            st.caption(f"Status: Round {st.session_state.current_round} ({st.session_state.scoring_mode})")
            if is_admin:
                with st.expander("Manage Roster"):
                    late_p = st.text_input("Add Late Player")
                    if st.button("Add Late"):
                        p_df = load_sheet("Players", force_refresh=True)
                        new_row = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": late_p}])
                        conn.update(worksheet="Players", data=pd.concat([p_df, new_row], ignore_index=True))
                        st.rerun()
                    
                    st.divider()
                    p_df = load_sheet("Players")
                    roster = p_df[p_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
                    p_to_drop = st.selectbox("Drop Player", ["--"] + roster)
                    if st.button("Drop Selected Player") and p_to_drop != "--":
                        drop_player(st.session_state.active_event_code, p_to_drop)
                        st.rerun()

        st.divider()
        if st.button("Sync Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        if is_admin:
            if st.button("End Tournament", type="secondary", use_container_width=True):
                st.session_state.active_event_code = ""
                st.session_state.current_pods = []
                st.session_state.draft_roster = []
                st.rerun()

# --- 7. MAIN UI ---
if st.session_state.active_event_code:
    st.title(f"Event: {st.session_state.active_event_code}")
    tab1, tab2, tab3 = st.tabs(["Leaderboard", "Active Pods", "History"])

    with tab1:
        if not event_history.empty:
            lb = event_history.groupby('Player').agg(
                Points=('Points', 'sum'), 
                Wins=('Result', lambda x: (x == 'Winner').sum())
            ).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else:
            st.info("No matches recorded yet.")

    with tab2:
        p_df = load_sheet("Players")
        existing = p_df[p_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
        full_roster = list(set(existing + st.session_state.draft_roster))

        if not st.session_state.current_pods:
            st.subheader("Roster Preview")
            st.write(f"Scoring: **{st.session_state.scoring_mode}**")
            st.write(", ".join(full_roster) if full_roster else "Add players in the sidebar.")
            
            if is_admin and len(full_roster) >= 4:
                if st.button("Start Tournament and Generate Pairings", type="primary"):
                    if st.session_state.draft_roster:
                        new_rows = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.draft_roster])
                        conn.update(worksheet="Players", data=pd.concat([p_df, new_rows], ignore_index=True))
                        st.session_state.draft_roster = []
                    
                    random.shuffle(full_roster)
                    st.session_state.current_pods = [full_roster[i:i+4] for i in range(0, len(full_roster), 4)]
                    st.rerun()
        else:
            st.subheader(f"Reporting Round {st.session_state.current_round}")
            results_data = []
            all_reported = True
            
            for i, pod in enumerate(st.session_state.current_pods):
                with st.expander(f"Pod {i+1}: {', '.join(pod)}", expanded=True):
                    if st.session_state.scoring_mode == "Casual":
                        win = st.selectbox("Winner", ["Select..."] + pod, key=f"win_{i}")
                        if win == "Select...":
                            all_reported = False
                        else:
                            for p in pod:
                                results_data.append({
                                    "event_code": st.session_state.active_event_code,
                                    "Round": st.session_state.current_round,
                                    "Player": p,
                                    "Points": 3 if p == win else 1,
                                    "Result": "Winner" if p == win else "Participant"
                                })
                    else:
                        # COMPETITIVE: MANUAL ENTRY (5, 3, 2, 1)
                        st.write("Enter points for each player:")
                        pod_points = {}
                        default_pts = [5, 3, 2, 1]
                        for idx, p in enumerate(pod):
                            pod_points[p] = st.number_input(
                                f"Points for {p}", 
                                min_value=0, max_value=10, 
                                value=default_pts[idx] if idx < len(default_pts) else 0, 
                                key=f"pts_{i}_{p}"
                            )
                        
                        max_p = max(pod_points.values())
                        for p, pts in pod_points.items():
                            results
