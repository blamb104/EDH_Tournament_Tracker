🛡️ EDH Tournament Tracker
A specialized tournament management tool designed specifically for Multiplayer Commander (EDH).

Unlike standard 1v1 Swiss software, this app is built to handle the unique social and mathematical challenges of 4-player pods. It balances competitive integrity with the "social contract" of Commander.

Key Features
Smart Pod Engine: Automatically calculates the optimal distribution of players. It prioritizes 4-person pods while intelligently shifting to 3-person pods (for example, turning 13 players into one 4-man and three 3-mans) to ensure no one is left playing a "1v1" or sitting out.

Dual Tournament Modes:
Casual Mode: Focuses on participation. The winner receives 4 points, while all other players receive 1 point for playing.
Competitive Mode: Uses a weighted ranking system (5/3/2/1 points) for 1st through 4th place.
The "Table Kill" Shortcut: A quality-of-life feature for Competitive mode. If a player combos off or eliminates the table simultaneously, a single toggle awards them 1st place and assigns the rest of the table "Last Place" (1 point) instantly.

Social Pairing Logic: The app tracks "Peer History." It runs 100 simulated shuffles every round to find the pairing with the lowest "Conflict Score," ensuring players don't get stuck playing against the same people multiple rounds in a row.

Live Leaderboard & Tiebreakers: Standings are calculated in real-time using Points, Wins, and OMP (Opponent Match Points). OMP serves as a strength-of-schedule tiebreaker, rewarding players who faced opponents with higher total scores.

Technical Stack
Language: Python
Framework: Streamlit (Web UI)
Data Handling: Pandas
Algorithm: Randomized Social-Conflict Minimization
