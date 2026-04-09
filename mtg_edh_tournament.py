import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet(name, force_refresh=False):
    """
    Loads data from Google Sheets. 
    Uses a 10-minute cache (600s) to prevent API Quota limits (429 errors).
    Set force_refresh=True when you need the most up-to-date data immediately.
    """
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
if 'current_round' not in st.session_state:
    st.session_state.current_round = 0
if 'active_event_code' not in st.session_state:
    st.session_state.active_event_code = ""

# --- 4. HELPER FUNCTIONS ---

def generate_unique_code():
    chars = string.ascii_uppercase + string.digits
    return "EDH-" + "".join(random.choice(chars) for _ in range(6))

def create_event(admin_email):
    df = load_sheet("Events", force_refresh=True)
    new_code = generate_unique_code()
    while new_code in df['event_code'].values:
        new_code = generate_unique_code()
    
    new_event = pd.DataFrame([{
        "event_code": new_code, 
        "admin_email": admin_email, 
        "status": "Active"
    }])
    updated = pd.concat([df, new_event], ignore_index=True)
    conn.update(worksheet="Events", data=updated)
    return new_code

def add_player(event_code, name):
    df = load_sheet("Players", force_refresh=True)
    if not ((df['event_code'] == event_code) & (df['player_name'] == name)).any():
        new_row = pd.DataFrame([{"event_code": event_code, "player_name": name}])
        updated = pd.concat([df, new_row], ignore_index=True)
        conn.update(worksheet="Players", data=updated)

def drop_player(event_code, name):
    df = load_sheet("Players", force_refresh=True)
    updated = df[~((df['event_code'] == event_code) & (df['player_name'] == name))]
    conn.update(worksheet="Players", data=updated)

# --- 5. SIDEBAR (Context-Aware Management) ---
with st.sidebar:
    # User Profile
    cols = st.columns([1, 4])
    cols[0].image(st.user.get("picture", "https://cdn-icons-png.flaticon.com/512/149/149071.png"), width=40)
    cols[1].write(f"**{st.user.get('name', 'User')}**")
    
    if st.button("Log Out"):
        st.logout()
    
    st.divider()

    # PHASE 1: NO EVENT CHOSEN
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

    # PHASE 2 & 3: EVENT ACTIVE
    else:
        st.subheader(f"Event: {st.session_state.active_event_code}")
        
        # Admin Validation
        events_df = load_sheet("Events")
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (event_row['admin_email'] == user_email)

        # Status Label
        if st.session_state.current_round == 0:
            st.caption("Status: Registration / Setup")
        else:
            st.caption(f"Status: Round {st.session_state.current_round} in Progress")

        # Admin Tools: Registration & Management
        if is_admin:
            if not st.session_state.current_pods:
                with st.form("add_player_form", clear_on_submit=True):
                    new_p = st.text_input("Register Player (Hit Enter)")
                    submitted = st.form_submit_button("Add to Roster")
                    if submitted and new_p:
                        add_player(st.session_state.active_event_code, new_p)
                        st.toast(f"Added {new_p}")
                        st.rerun()
            else:
                st.write("---")
                players_df = load_sheet("Players")
                roster = players_df[players_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
                p_to_drop = st.selectbox("Drop Player", ["--"] + roster)
                if st.button("Drop Player") and p_to_drop != "--":
                    drop_player(st.session_state.active_event_code, p_to_drop)
                    st.toast(f"Removed {p_to_drop}")
                    st.rerun()

        st.divider()

        if st.button("Sync Data", use_container_width=True):
            st.cache_data.clear()
            st.toast("Data resynced")
            st.rerun()

        if is_admin:
            if st.button("End Tournament", type="secondary", use_container_width=True):
                st.session_state.active_event_code = ""
                st.session_state.current_pods = []
                st.session_state.current_round = 0
                st.rerun()

# --- 6. MAIN UI ---
if st.session_state.active_event_code:
    event_code = st.session_state.active_event_code
    st.title(f"Event: {event_code}")

    tab1, tab2, tab3 = st.tabs(["Leaderboard", "Active Pods", "History"])

    with tab1:
        hist_df = load_sheet("MatchHistory")
        event_hist = hist_df[hist_df['event_code'] == event_code]
        
        if not event_hist.empty:
            leaderboard = event_hist.groupby('Player').agg(
                Total_Points=('Points', 'sum'),
                Matches_Played=('Player', 'count'),
                Wins=('Result', lambda x: (x == 'Winner').sum())
            ).sort_values(by=['Total_Points', 'Wins'], ascending=False)
            st.dataframe(leaderboard, use_container_width=True)
        else:
            st.info("No matches recorded yet.")

    with tab2:
        players_df = load_sheet("Players")
        roster = players_df[players_df['event_code'] == event_code]['player_name'].tolist()

        if not st.session_state.current_pods:
            st.subheader("Roster")
            st.write(", ".join(roster) if roster else "No players registered.")
            
            if is_admin and len(roster) >= 4:
                if st.button("Generate Pairings", type="primary"):
                    random.shuffle(roster)
                    st.session_state.current_pods = [roster[i:i + 4] for i in range(0, len(roster), 4)]
                    st.session_state.current_round += 1
                    st.rerun()
        else:
            st.subheader(f"Round {st.session_state.current_round} Results")
            results_data = []
            all_reported = True
            
            for i, pod in enumerate(st.session_state.current_pods):
                with st.expander(f"Pod {i+1}: {', '.join(pod)}", expanded=True):
                    win = st.selectbox("Who won?", ["Select..."] + pod, key=f"pod_{i}")
                    if win == "Select...":
                        all_reported = False
                    else:
                        for p in pod:
                            results_data.append({
                                "event_code": event_code,
                                "Round": st.session_state.current_round,
                                "Player": p,
                                "Points": 4 if p == win else 1,
                                "Result": "Winner" if p == win else "Participant"
                            })
            
            if is_admin and st.button("Finalize and Upload Results", disabled=not all_reported):
                full_hist = load_sheet("MatchHistory", force_refresh=True)
                updated_hist = pd.concat([full_hist, pd.DataFrame(results_data)], ignore_index=True)
                conn.update(worksheet="MatchHistory", data=updated_hist)
                st.session_state.current_pods = []
                st.rerun()

    with tab3:
        st.header("Event History")
        full_hist = load_sheet("MatchHistory")
        st.dataframe(full_hist[full_hist['event_code'] == event_code], use_container_width=True)
