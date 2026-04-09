import streamlit as st
import pandas as pd
import random
import string
from streamlit_gsheets import GSheetsConnection

# --- 1. INITIAL SETUP & CONNECTION ---
st.set_page_config(page_title="EDH Tournament Tracker", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. GLOBAL DATA LOAD (Prevents repetitive API calls) ---
@st.cache_data(ttl=600)
def get_all_data():
    events = conn.read(worksheet="Events")
    players = conn.read(worksheet="Players")
    history = conn.read(worksheet="MatchHistory")
    # We'll use a 'CurrentPods' sheet to sync the active round across users
    active_pods = conn.read(worksheet="CurrentPods")
    return events, players, history, active_pods

events_df, players_df, history_df, active_pods_df = get_all_data()

# --- 3. SESSION STATE ---
if 'active_event_code' not in st.session_state:
    st.session_state.active_event_code = ""

user_email = st.user.get("email").lower() if st.user.get("is_logged_in") else None

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("Settings")
    if not st.user.get("is_logged_in"):
        if st.button("Admin Login"): st.login()
    else:
        st.write(f"Logged in: **{st.user.get('name')}**")
        if st.button("Log Out"): st.logout()
    
    st.divider()

    if not st.session_state.active_event_code:
        input_code = st.text_input("Enter Event Code:").upper().strip()
        if st.button("Load Event"):
            if input_code in events_df['event_code'].values:
                st.session_state.active_event_code = input_code
                st.rerun()
            else: st.error("Invalid Code")
    else:
        # Check Admin Status
        event_row = events_df[events_df['event_code'] == st.session_state.active_event_code].iloc[0]
        is_admin = (user_email == event_row['admin_email'].lower()) if user_email else False

        st.subheader(f"Code: {st.session_state.active_event_code}")
        
        if is_admin:
            st.success("Admin Mode")
            if st.button("Sync Data", use_container_width=True):
                st.cache_data.clear(); st.rerun()
            if st.button("End Tournament", use_container_width=True, type="primary"):
                # Clean up active pods on end
                clean_pods = active_pods_df[active_pods_df['event_code'] != st.session_state.active_event_code]
                conn.update(worksheet="CurrentPods", data=clean_pods)
                st.session_state.active_event_code = ""; st.cache_data.clear(); st.rerun()
        else:
            if st.button("Exit Event"):
                st.session_state.active_event_code = ""; st.rerun()

# --- 5. MAIN UI ---
if st.session_state.active_event_code:
    # Filter data for this specific event
    this_event_history = history_df[history_df['event_code'] == st.session_state.active_event_code].copy()
    this_event_players = players_df[players_df['event_code'] == st.session_state.active_event_code]['player_name'].tolist()
    this_event_pods = active_pods_df[active_pods_df['event_code'] == st.session_state.active_event_code]
    
    current_round = int(this_event_history['Round'].max() + 1) if not this_event_history.empty else 1
    
    st.title(f"🛡️ EDH Tournament: {st.session_state.active_event_code}")
    tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "⚔️ Active Pods", "📜 Match History"])
    
    with tab1:
        if not this_event_history.empty:
            this_event_history['Points'] = this_event_history['Points'].astype(int)
            lb = this_event_history.groupby('Player').agg(Points=('Points', 'sum'), Wins=('Result', lambda x: (x == 'Winner').sum())).sort_values(by=['Points', 'Wins'], ascending=False)
            st.dataframe(lb, use_container_width=True)
        else: st.info("Leaderboard will populate after Round 1.")

    with tab2:
        # If no pods are saved in the sheet for this event
        if this_event_pods.empty:
            if is_admin:
                st.subheader(f"Prepare Round {current_round}")
                if st.button(f"Generate & Publish Round {current_round}", type="primary"):
                    # Swiss Logic (Simplified for brevity)
                    random.shuffle(this_event_players) 
                    new_pods_list = [this_event_players[i:i + 4] for i in range(0, len(this_event_players), 4)]
                    
                    # Save to CurrentPods sheet so others can see it
                    rows = []
                    for i, pod in enumerate(new_pods_list):
                        for p in pod:
                            rows.append({"event_code": st.session_state.active_event_code, "Pod": i+1, "Player": p})
                    
                    updated_pods = pd.concat([active_pods_df, pd.DataFrame(rows)], ignore_index=True)
                    conn.update(worksheet="CurrentPods", data=updated_pods)
                    st.cache_data.clear(); st.rerun()
            else:
                st.info(f"Waiting for Admin to publish Round {current_round}...")
        
        else:
            # Pods exist in the sheet!
            st.subheader(f"Active Pairings: Round {current_round}")
            pod_ids = sorted(this_event_pods['Pod'].unique())
            res_rows = []
            ready_to_finalize = True
            
            for pid in pod_ids:
                pod_members = this_event_pods[this_event_pods['Pod'] == pid]['Player'].tolist()
                with st.expander(f"Pod {pid}: {', '.join(pod_members)}", expanded=True):
                    if is_admin:
                        win = st.selectbox("Select Winner", ["--"] + pod_members, key=f"p{pid}")
                        if win == "--": ready_to_finalize = False
                        else:
                            for p in pod_members:
                                res_rows.append({"event_code": st.session_state.active_event_code, "Round": current_round, "Pod": pid, "Player": p, "Points": 3 if p == win else 1, "Result": "Winner" if p == win else "Participant"})
                    else:
                        for p in pod_members: st.write(f"• {p}")

            if is_admin:
                if st.button("Finalize Round", disabled=not ready_to_finalize, type="primary"):
                    # 1. Update MatchHistory
                    new_hist = pd.concat([history_df, pd.DataFrame(res_rows)], ignore_index=True)
                    conn.update(worksheet="MatchHistory", data=new_hist)
                    # 2. Clear CurrentPods for this event
                    remaining_pods = active_pods_df[active_pods_df['event_code'] != st.session_state.active_event_code]
                    conn.update(worksheet="CurrentPods", data=remaining_pods)
                    st.cache_data.clear(); st.rerun()

    with tab3:
        if not this_event_history.empty:
            for r in sorted(this_event_history['Round'].unique(), reverse=True):
                with st.expander(f"Round {int(r)}"):
                    rd = this_event_history[this_event_history['Round'] == r]
                    for p_num in sorted(rd['Pod'].unique()):
                        p_data = rd[rd['Pod'] == p_num]
                        st.markdown(f"**Pod {int(p_num)}: {', '.join(p_data['Player'].tolist())}**")
                        st.table(p_data[["Player", "Result", "Points"]])
        else: st.info("No match history recorded yet.")
