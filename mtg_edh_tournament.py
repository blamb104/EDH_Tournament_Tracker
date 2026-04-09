import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet(name):
    # ttl="0" ensures we always get the freshest data from Google
    return conn.read(worksheet=name, ttl="0")

# --- 2. AUTHENTICATION ---
if not st.user.get("is_logged_in"):
    st.title("🛡️ EDH Tournament Portal")
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
    df = load_sheet("Events")
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
    df = load_sheet("Players")
    if not ((df['event_code'] == event_code) & (df['player_name'] == name)).any():
        new_row = pd.DataFrame([{"event_code": event_code, "player_name": name}])
        updated = pd.concat([df, new_row], ignore_index=True)
        conn.update(worksheet="Players", data=updated)

# --- SIDEBAR LOGIC ---
with st.sidebar:
    # 1. User Identity
    cols = st.columns([1, 4])
    cols[0].image(st.user.get("picture", "https://icon-library.com/images/default-user-icon/default-user-icon-13.jpg"), width=40)
    cols[1].write(f"**{st.user.get('name', 'User')}**")
    
    st.divider()

    # PHASE 1: NO EVENT SELECTED
    if not st.session_state.active_event_code:
        st.subheader("Tournament Hub")
        if st.button("Create New Event", use_container_width=True):
            new_code = create_event(user_email)
            st.session_state.active_event_code = new_code
            st.rerun()
            
        join_code = st.text_input("Or Join Existing Code:").upper().strip()
        if join_code:
            # (Validation logic from before...)
            st.session_state.active_event_code = join_code
            st.rerun()

    # PHASE 2 & 3: EVENT ACTIVE
    else:
        st.subheader(f"🏆 {st.session_state.active_event_code}")
        
        # Check if we are the admin
        events_df = load_sheet("Events")
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (event_row['admin_email'] == user_email)

        if not st.session_state.current_pods:
            # TOURNAMENT SETUP MODE
            st.caption("Status: Registration Open")
            if is_admin:
                with st.form("add_player_form", clear_on_submit=True):
                    new_p = st.text_input("Register Player:")
                    submitted = st.form_submit_button("Add to Roster")
                    if submitted and new_p:
                        add_player(st.session_state.active_event_code, new_p)
                        st.toast(f"✅ {new_p} added!")
                        st.rerun()
        else:
            # EVENT MANAGER MODE
            st.caption("Status: Round {st.session_state.current_round} in Progress")
            if is_admin:
                st.write("---")
                st.subheader("Drop Players")
                players_df = load_sheet("Players")
                roster = players_df[players_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
                player_to_drop = st.selectbox("Select Player to Drop", ["--"] + roster)
                if st.button("❌ Drop Player") and player_to_drop != "--":
                    # (Add logic to remove from Players sheet)
                    st.warning(f"{player_to_drop} removed.")

        st.divider()
        
        # FINAL ACTIONS
        if is_admin:
            if st.button("End Tournament", type="secondary", use_container_width=True):
                # We can add a "Archive" logic here
                st.session_state.active_event_code = ""
                st.session_state.current_pods = []
                st.rerun()
        
        # CSV DOWNLOAD (Available to all)
        hist_df = load_sheet("MatchHistory")
        final_data = hist_df[hist_df['event_code'] == st.session_state.active_event_code]
        if not final_data.empty:
            csv = final_data.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV Results",
                data=csv,
                file_name=f"{st.session_state.active_event_code}_results.csv",
                mime='text/csv',
                use_container_width=True
            )

# --- 6. MAIN UI ---
event_code = st.session_state.active_event_code
st.title(f"🛡️ Event: {event_code}")

tab1, tab2, tab3 = st.tabs(["🏆 Leaderboard", "⚔️ Active Pods", "📜 History"])

with tab1:
    st.header("🏆 Leaderboard")
    hist_df = load_sheet("MatchHistory")
    event_hist = hist_df[hist_df['event_code'] == event_code]
    
    if not event_hist.empty:
        # Group by player and sum points
        leaderboard = event_hist.groupby('Player').agg({
            'Points': 'sum',
            'Result': lambda x: (x == 'Winner').sum()
        }).rename(columns={'Result': 'Wins'}).sort_values(by=['Points', 'Wins'], ascending=False)
        st.dataframe(leaderboard, use_container_width=True)
    else:
        st.info("No matches recorded.")

with tab2:
    players_df = load_sheet("Players")
    roster = players_df[players_df['event_code'] == event_code]['player_name'].tolist()

    if not st.session_state.current_pods:
        st.subheader("Manage Roster")
        if is_admin:
            new_p = st.text_input("Add Player Name")
            if st.button("Register Player"):
                add_player(event_code, new_p)
                st.rerun()
        
        st.write(f"**Players ({len(roster)}):** " + ", ".join(roster))
        
        if len(roster) >= 4 and is_admin:
            if st.button("🚀 Generate Pairings", type="primary"):
                random.shuffle(roster)
                st.session_state.current_pods = [roster[i:i + 4] for i in range(0, len(roster), 4)]
                st.session_state.current_round += 1
                st.rerun()
    else:
        # REPORTING SECTION
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
        
        if is_admin and st.button("✅ Finalize & Upload Results", disabled=not all_reported):
            full_hist = load_sheet("MatchHistory")
            updated_hist = pd.concat([full_hist, pd.DataFrame(results_data)], ignore_index=True)
            conn.update(worksheet="MatchHistory", data=updated_hist)
            st.session_state.current_pods = []
            st.rerun()

with tab3:
    st.header("📜 Event History")
    event_hist = load_sheet("MatchHistory")
    st.dataframe(event_hist[event_hist['event_code'] == event_code], use_container_width=True)
