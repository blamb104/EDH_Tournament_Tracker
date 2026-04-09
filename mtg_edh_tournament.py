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
if 'current_pods' not in st.session_state:
    st.session_state.current_pods = []
if 'active_event_code' not in st.session_state:
    st.session_state.active_event_code = ""
if 'current_round' not in st.session_state:
    st.session_state.current_round = 1
if 'draft_roster' not in st.session_state:
    st.session_state.draft_roster = []
if 'scoring_mode' not in st.session_state:
    st.session_state.scoring_mode = "Casual"

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
    conn.update(worksheet="Events", data=pd.concat([df, new_event], ignore_index=True))
    return new_code

def drop_player(event_code, name):
    df = load_sheet("Players", force_refresh=True)
    updated = df[~((df['event_code'] == event_code) & (df['player_name'] == name))]
    conn.update(worksheet="Players", data=updated)

# --- 5. DATA SYNC & INITIAL ROUND LOAD ---
# This only runs when you first enter an event or hit "Sync"
if st.session_state.active_event_code and len(st.session_state.current_pods) == 0:
    hist_df = load_sheet("MatchHistory")
    event_history = hist_df[hist_df['event_code'] == st.session_state.active_event_code]
    if not event_history.empty:
        # Sync the local round counter to whatever is in the sheet
        st.session_state.current_round = int(event_history['Round'].max()) + 1
    else:
        st.session_state.current_round = 1
else:
    # Use existing history from cache if available
    hist_df = load_sheet("MatchHistory")
    event_history = hist_df[hist_df['event_code'] == st.session_state.active_event_code] if st.session_state.active_event_code else pd.DataFrame()

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
        if not has_started:
            st.caption("Status: Registration Open")
            if is_admin:
                st.session_state.scoring_mode = st.radio("Scoring System", ["Casual", "Competitive"])
                with st.form("add_player_form", clear_on_submit=True):
                    new_p = st.text_input("Draft Player")
                    if st.form_submit_button("Add to List") and new_p:
                        if new_p not in st.session_state.draft_roster:
                            st.session_state.draft_roster.append(new_p)
                            st.rerun()
        else:
            st.caption(f"Status: Round {st.session_state.current_round} ({st.session_state.scoring_mode})")
            if is_admin:
                with st.expander("Manage Roster"):
                    late_p = st.text_input("Add Late Player")
                    if st.button("Add Late"):
                        p_df = load_sheet("Players", force_refresh=True)
                        conn.update(worksheet="Players", data=pd.concat([p_df, pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": late_p}])], ignore_index=True))
                        st.rerun()

        st.divider()
        if st.button("Sync Data", use_container_width=True):
            st.cache_data.clear()
            st.session_state.current_pods = [] # Force a re-fetch of round state
            st.rerun()
        if is_admin and st.button("End Tournament", type="secondary", use_container_width=True):
            st.session_state.active_event_code = ""; st.session_state.current_pods = []; st.session_state.draft_roster = []; st.rerun()

# --- 7. MAIN UI ---
if st.session_state.active_event_code:
    st.title(f"Event: {st.session_state.active_event_code}")
    tab1, tab2, tab3 = st.tabs(["Leaderboard", "Active Pods", "History"])

    with tab1:
        if not event_history.empty:
            lb = event_history.groupby('Player').agg(Points=('Points', 'sum'), Wins=('Result', lambda x: (x == 'Winner').sum())).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else: st.info("No matches recorded yet.")

    with tab2:
        p_df = load_sheet("Players")
        existing = p_df[p_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
        full_roster = list(set(existing + st.session_state.draft_roster))

        if not st.session_state.current_pods:
            st.subheader(f"Prepare Round {st.session_state.current_round}")
            if is_admin and len(full_roster) >= 4:
                if st.button(f"Generate Round {st.session_state.current_round}", type="primary"):
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
                        if win == "Select...": all_reported = False
                        else:
                            for p in pod: results_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        st.write("Enter points (5, 3, 2, 1):")
                        pod_points = {}
                        default_pts = [5, 3, 2, 1]
                        for idx, p in enumerate(pod):
                            pod_points[p] = st.number_input(f"Points for {p}", 0, 10, default_pts[idx] if idx < len(default_pts) else 0, key=f"pts_{i}_{p}")
                        max_p = max(pod_points.values())
                        for p, pts in pod_points.items(): results_data.append({"event_code": st.session_state.active_event_code, "Round": st.session_state.current_round, "Player": p, "Points": pts, "Result": "Winner" if pts == max_p and pts > 0 else "Participant"})

            if is_admin and st.button("Finalize and Upload Results", disabled=not all_reported):
                hist = load_sheet("MatchHistory", force_refresh=True)
                conn.update(worksheet="MatchHistory", data=pd.concat([hist, pd.DataFrame(results_data)], ignore_index=True))
                
                # --- LOCAL TRACKING UPDATES ---
                st.session_state.current_pods = [] # Clear pods locally
                st.session_state.current_round += 1 # Increment round locally
                st.cache_data.clear() # Refresh leaderboard data
                st.rerun()

    with tab3:
        st.header("Event History")
        st.dataframe(event_history, use_container_width=True)
