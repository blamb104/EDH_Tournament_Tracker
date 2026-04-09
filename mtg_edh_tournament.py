import streamlit as st
import pandas as pd
import random
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet(name):
    return conn.read(worksheet=name, ttl="0")

# --- 2. AUTHENTICATION ---
if not st.user.get("is_logged_in"):
    st.title("🛡️ EDH Tournament Portal")
    st.info("Log in to manage tournaments or report results.")
    if st.button("Log in with Google"):
        st.login()
    st.stop()

user_email = st.user.get("email")

# --- 3. SESSION STATE (Local overrides) ---
if 'current_pods' not in st.session_state:
    st.session_state.current_pods = []
if 'current_round' not in st.session_state:
    st.session_state.current_round = 0

# --- 4. SIDEBAR & EVENT SETUP ---
with st.sidebar:
    st.markdown("---")
    cols = st.columns([1, 4])
    # Show user's profile picture if available, else a generic icon
    with cols[0]:
        st.image(st.user.get("picture", "https://cdn-icons-png.flaticon.com/512/149/149071.png"), width=40)
    with cols[1]:
        st.write(f"**{st.user.get('name', 'User')}**")
        st.caption(user_email)
    
    # Add a logout button for convenience
    if st.button("Log Out", use_container_width=True):
        st.logout()
    st.markdown("---")
    st.title("Tournament Setup")
    event_code = st.text_input("Event Code", placeholder="e.g. FNM_MARCH")
    mode = st.radio("Tournament Mode", ["Casual", "Competitive"])
    
    if not event_code:
        st.warning("Enter an Event Code to begin.")
        st.stop()
        
    st.success(f"Event: {event_code}")
    st.write(f"User: {user_email}")

# --- 5. LOGIC FUNCTIONS (Sheets Integrated) ---

def add_player_to_sheet(name):
    df = load_sheet("Players")
    if not ((df['event_code'] == event_code) & (df['player_name'] == name)).any():
        new_player = pd.DataFrame([{"event_code": event_code, "player_name": name, "email": ""}])
        updated = pd.concat([df, new_player], ignore_index=True)
        conn.update(worksheet="Players", data=updated)

def get_standings():
    history_df = load_sheet("MatchHistory")
    event_data = history_df[history_df['event_code'] == event_code]
    if event_data.empty: return pd.DataFrame()
    
    # Simple grouping logic
    summary = event_data.groupby('Player').agg({'Points': 'sum'}).reset_index()
    return summary.sort_values(by='Points', ascending=False)

# --- 6. MAIN UI ---
st.title(f"⚔️ {event_code} Tracker")
tab1, tab2, tab3 = st.tabs(["🏆 Leaderboard", "⚔️ Active Pods", "📜 Match History"])

with tab1:
    df_leader = get_standings()
    if not df_leader.empty:
        st.dataframe(df_leader, use_container_width=True, hide_index=True)
    else:
        st.info("No matches recorded yet.")

with tab2:
    # Logic to fetch players for this event
    players_df = load_sheet("Players")
    current_players = players_df[players_df['event_code'] == event_code]['player_name'].tolist()
    
    if not st.session_state.current_pods:
        if len(current_players) < 4:
            st.warning("Need at least 4 players registered for this event code.")
            player_name = st.text_input("Register Player Name")
            if st.button("Add Player"):
                add_player_to_sheet(player_name)
                st.rerun()
        else:
            if st.button("Generate Next Round"):
                # Your pod generation logic here (simplified for space)
                random.shuffle(current_players)
                st.session_state.current_pods = [current_players[i:i + 4] for i in range(0, len(current_players), 4)]
                st.session_state.current_round += 1
                st.rerun()
    else:
        # RESULTS REPORTING
        st.subheader(f"Round {st.session_state.current_round}")
        results_to_save = []
        for i, pod in enumerate(st.session_state.current_pods):
            with st.expander(f"Pod {i+1}"):
                winner = st.selectbox("Winner", ["Select..."] + pod, key=f"win_{i}")
                if winner != "Select...":
                    for p in pod:
                        results_to_save.append({
                            "event_code": event_code,
                            "round": st.session_state.current_round,
                            "Player": p,
                            "Points": 4 if p == winner else 1,
                            "Result": "Winner" if p == winner else "Participant"
                        })
        
        if st.button("Finalize Round"):
            history_df = load_sheet("MatchHistory")
            new_data = pd.DataFrame(results_to_save)
            updated_history = pd.concat([history_df, new_data], ignore_index=True)
            conn.update(worksheet="MatchHistory", data=updated_history)
            st.session_state.current_pods = []
            st.success("Round saved to Google Sheets!")
            st.rerun()
