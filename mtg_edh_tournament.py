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
    'draft_roster': [],
    'scoring_mode': "Casual"
}
for key, val in states.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 4. CALLBACKS & HELPERS ---
def add_player_callback():
    """Ensures players are added to the list properly from the form."""
    new_p = st.session_state.player_input_field.strip()
    if new_p and new_p not in st.session_state.draft_roster:
        st.session_state.draft_roster.append(new_p)
    # Clear input field manually
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

def drop_player(event_code, name):
    df = load_sheet("Players", force_refresh=True)
    updated = df[~((df['event_code'] == event_code) & (df['player_name'] == name))]
    conn.update(worksheet="Players", data=updated)

# --- 5. DATA PERSISTENCE & ROUND TRACKING ---
if st.session_state.active_event_code:
    hist_df = load_sheet("MatchHistory")
    event_history = hist_df[hist_df['event_code'] == st.session_state.active_event_code]
    
    # Only reset round from sheet if we aren't currently mid-tournament locally
    if not event_history.empty and not st.session_state.current_pods:
        max_r = int(event_history['Round'].max())
        st.session_state.current_round = max_r + 1
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
        else:
            st.warning("Host access required.")
        input_code = st.text_input("Enter Event Code:").upper().strip()
        if input_code:
            events_df = load_sheet("Events")
            if input_code in events_df['event_code'].values:
                st.session_state.active_event_code = input_code
                st.rerun()
    else:
        # --- ACTIVE EVENT SIDEBAR ---
        events_df = load_sheet("Events")
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (event_row['admin_email'] == user_email)
        
        st.subheader(f"Event: {st.session_state.active_event_code}")
        has_started = not event_history.empty or len(st.session_state.current_pods) > 0
        
        if not has_started:
            st.caption("Status: Registration Open")
            if is_admin:
                # SCORING WITH INFO BOXES (TOOLTIPS)
                st.session_state.scoring_mode = st.radio(
                    "Scoring System", ["Casual", "Competitive"],
                    help="**Casual**: 3 pts for a win, 1 pt for playing.\n\n**Competitive**: Manual entry. Defaults to 5 pts (1st), 3 pts (2nd), 2 pts (3rd), 1 pt (4th)."
                )
                
                st.write("### Add Players")
                with st.form("add_player_form", clear_on_submit=True):
                    st.text_input("Player Name", key="player_input_field")
                    st.form_submit_button("Add to List", on_click=add_player_callback)
                
                # VISIBLE PREVIEW LIST
                if st.session_state.draft_roster:
                    st.write(f"**Drafting ({len(st.session_state.draft_roster)})**")
                    for p in st.session_state.draft_roster:
                        st.text(f"• {p}")
                    if st.button("Clear Draft"):
                        st.session_state.draft_roster = []
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
        # Combine local draft with sheet data
        full_roster = list(set(existing + st.session_state.draft_roster))

        if not st.session_state.current_pods:
            st.subheader(f"Prepare Round {st.session_state.current_round}")
            st.write(f"Confirmed Players: {len(full_roster)}")
            
            if is_admin and len(full_roster) >= 4:
                if st.button(f"Generate Round {st.session_state.current_round}", type="primary"):
                    # Push draft to sheet only when round starts
                    if st.session_state.draft_roster:
                        new_rows = pd.DataFrame([{"event_code": st.session_state.active_event_code, "player_name": p} for p in st.session_state.draft_roster])
                        conn.update(worksheet="Players", data=pd.concat([p_df, new_rows], ignore_index=True))
                        st.session_state.draft_roster = []
                    
                    random.shuffle(full_roster)
                    st.session_state.current_pods = [full_roster[i:i+4] for i in range(0, len(full_roster), 4)]
                    st.rerun()
            elif len(full_roster) < 4:
                st.warning("Need at least 4 players to generate pods.")
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
                st.session_state.current_pods = []
                st.session_state.current_round += 1
                st.cache_data.clear() 
                st.rerun()

    with tab3:
        st.header("Event History")
        st.dataframe(event_history, use_container_width=True)
