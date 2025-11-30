import requests
import time
import os
import urllib3
from .config import Config
from .state import state
from .utils import get_loader_html, filter_events, prune_data, get_windows_host_ip
from .ai import ai

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def poll_lol_api():
    # Determine target IP
    target_ip = Config.WINDOWS_HOST
    
    if not target_ip and "microsoft" in os.uname().release.lower():
        print("WSL2 detected. Attempting to find Windows host IP...", flush=True)
        target_ip = get_windows_host_ip()
        print(f"Targeting Windows Host at: {target_ip}", flush=True)
    
    if not target_ip:
        target_ip = "127.0.0.1"
    
    print(f"Starting LoL API polling thread (Target: {target_ip})...", flush=True)
    while True:
        try:
            # Poll local LoL API
            response = requests.get(
                f"https://{target_ip}:{Config.LOL_API_PORT}/liveclientdata/allgamedata", 
                verify=False, 
                timeout=2.0
            )
            
            if response.status_code == 200:
                raw_data = response.json()
                less_events_data = filter_events(raw_data, seconds=120)
                clean_data = prune_data(less_events_data)
                
                # Extract Game Mode & Time
                game_data = raw_data.get('gameData', {})
                game_mode = game_data.get('gameMode', 'UNKNOWN')
                game_time = game_data.get('gameTime', 0)
                state.current_game_mode = game_mode
                
                # Extract Player Info & Teams
                active_player_name = raw_data.get('activePlayer', {}).get('summonerName', 'Unknown')
                all_players = raw_data.get('allPlayers', [])
                
                my_team = []
                enemy_team = []
                my_champion = "Unknown"
                my_position = "UNKNOWN"
                direct_opponent = "Inconnu"
                
                for p in all_players:
                    champ = p.get('championName', 'Unknown')
                    name = p.get('summonerName', '')
                    team = p.get('team', '')
                    position = p.get('position', '')
                    
                    if name == active_player_name:
                        my_champion = champ
                        my_team_id = team
                        my_position = position
                        
                # Second pass to sort teams and find opponent
                for p in all_players:
                    champ = p.get('championName', 'Unknown')
                    team = p.get('team', '')
                    position = p.get('position', '')
                    
                    if team == my_team_id:
                        my_team.append(champ)
                    else:
                        enemy_team.append(champ)
                        if position == my_position and position != "":
                            direct_opponent = champ

                # Save valid game data for post-game analysis
                state.last_valid_game_data = raw_data

                # Generate Advice
                ai.generate_advice(
                    clean_data, game_time, my_champion, my_position, 
                    direct_opponent, my_team, enemy_team, game_mode
                )

            else:
                print(f"API returned non-200 status: {response.status_code}", flush=True)
                state.latest_advice = get_loader_html("Partie détectée. En attente de l'initialisation de l'API...")
                state.current_game_mode = "Unknown"
            
        except requests.exceptions.ConnectionError:
            print("Connection Error: Game probably not running or API not accessible.", flush=True)
            
            # POST-GAME ANALYSIS
            if state.last_valid_game_data:
                full_game_data = prune_data(state.last_valid_game_data)
                ai.generate_post_game_report(full_game_data)
            else:
                state.latest_advice = get_loader_html("En attente du lancement de la partie...")
                state.current_game_mode = "Offline"
            pass
        except Exception as e:
            print(f"Polling Error: {e}", flush=True)
            state.latest_advice = f"❌ Erreur technique : {str(e)}"
            state.current_game_mode = "Error"
            
        # Adaptive polling strategy
        current_time = time.time()
        if ai.model and (current_time - state.last_gemini_call < (Config.AI_UPDATE_INTERVAL - 10)):
             # If we just called Gemini, we can sleep longer
            time.sleep(Config.POLL_INTERVAL_SLOW)
        else:
            # If we are close to the window or disconnected, poll faster
            time.sleep(Config.POLL_INTERVAL_FAST)
