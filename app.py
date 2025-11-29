import threading
import time
import json
import requests
import google.generativeai as genai
from flask import Flask, render_template
import os
import urllib3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
API_KEY = os.environ.get("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    try:
        model = genai.GenerativeModel(model_name)
        print(f"Gemini model initialized: {model_name}", flush=True)
    except Exception as e:
        print(f"Error initializing Gemini model {model_name}: {e}", flush=True)
        model = None
else:
    print("Error: GEMINI_API_KEY not found in environment variables.", flush=True)
    model = None

app = Flask(__name__)

# Global state
latest_advice = "En attente du lien neural avec la Faille de l'invocateur..."
last_gemini_call = 0
advice_history = []
current_game_mode = "Unknown"
last_advice_gametime = "00:00"
debug_mode = False

def get_loader_html(message="Analyse en cours..."):
    return f"""
    <div class="flex flex-col items-center justify-center h-48 text-hextech-blue/50 animate-pulse">
        <svg class="w-12 h-12 mb-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <p>{message}</p>
    </div>
    """

# Initialize latest_advice with loader
latest_advice = get_loader_html("En attente du lien neural avec la Faille de l'invocateur...")

def format_gametime(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02}:{secs:02}"

def filter_events(game_data, seconds=120):
    """
    Ne conserve que les événements survenus dans les 'seconds' dernières secondes.
    Si le JSON est incomplet (début de chargement), on le retourne tel quel.
    """
    try:
        # On vérifie que les données nécessaires existent
        if 'gameData' not in game_data or 'events' not in game_data:
            return game_data
            
        current_time = game_data['gameData']['gameTime']
        events_list = game_data['events'].get('Events', [])
        
        # Filtrage : On garde l'event si (TempsEvent > TempsActuel - 120s)
        recent_events = [
            event for event in events_list 
            if event['EventTime'] > (current_time - seconds)
        ]
        
        # On remplace la liste originale par la version filtrée
        game_data['events']['Events'] = recent_events
        return game_data

    except Exception as e:
        # En cas de structure imprévue, on ne casse pas le programme, on renvoie la data
        # print(f"Warning filtering events: {e}") 
        return game_data

def prune_data(data):
    """
    Nettoie récursivement le JSON pour l'IA.
    - Supprime les descriptions, skins, IDs internes, et données statiques.
    - Simplifie drastiquement la liste des items.
    """
    
    # Liste noire : Clés à supprimer sans pitié
    KEYS_TO_REMOVE = {
        'rawDescription', 'rawDisplayName', 'rawChampionName', 
        'rawSkinName', 'skinName', 'skinID', 
        'riotId', 'riotIdGameName', 'riotIdTagLine', 'summonerName', 
        'fullRunes',  # Trop verbeux, 'runes' simple suffit
        'abilities',  # L'IA connait déjà les sorts des champions par cœur
        'summonerSpells' # On garde les spells dans 'allPlayers', mais on vire les détails ici si besoin
    }

    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            # 1. Si la clé est dans la liste noire, on saute
            if k in KEYS_TO_REMOVE:
                continue

            # 2. Optimisation Spéciale : ITEMS
            # Au lieu de garder tout l'objet item, on garde juste Nom, ID et Nombre
            if k == 'items' and isinstance(v, list):
                new_dict[k] = [
                    {
                        'id': item.get('itemID'),
                        'name': item.get('displayName'),
                        'count': item.get('count'),
                        'slot': item.get('slot')
                    }
                    for item in v
                ]
                continue
            
            # 3. Optimisation Spéciale : SUMMONER SPELLS
            # On ne garde que le nom du sort (ex: "Flash"), pas la description
            if k == 'summonerSpells' and isinstance(v, dict):
                simplified_spells = {}
                for spell_key, spell_data in v.items():
                     simplified_spells[spell_key] = spell_data.get('displayName', 'Unknown')
                new_dict[k] = simplified_spells
                continue

            # 4. Récursion standard pour le reste
            new_dict[k] = prune_data(v)
            
        return new_dict

    elif isinstance(data, list):
        return [prune_data(item) for item in data]

    else:
        return data

def get_windows_host_ip():
    """
    Tries to detect the Windows host IP when running in WSL2.
    """
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if "nameserver" in line:
                    return line.split()[1]
    except:
        pass
    return "127.0.0.1"

def poll_lol_api():
    global latest_advice, last_gemini_call, advice_history, current_game_mode, last_advice_gametime
    
    last_valid_game_data = None
    
    # Determine target IP
    target_ip = os.environ.get("WINDOWS_HOST")
    
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
                f"https://{target_ip}:2999/liveclientdata/allgamedata", 
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
                current_game_mode = game_mode
                
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
                last_valid_game_data = raw_data

                # Check if we should call Gemini (every 2 minutes)
                current_time = time.time()
                if model and (current_time - last_gemini_call > 120):
                    try:
                        # Keep only last 3 advices for context
                        context_history = advice_history[-3:] if advice_history else "Aucun historique."
                        
                        # EARLY GAME STRATEGY (< 2 minutes)
                        if game_time < 120:
                            print("Generating Early Game Plan...", flush=True)
                            latest_advice = get_loader_html("Génération du plan de jeu (Early Game)...")
                            prompt = (
                                "Tu es un coach Challenger sur League of Legends. "
                                "La partie vient de commencer. Donne un plan de jeu complet.\n\n"
                                f"JOUEUR: {my_champion} (Moi) - Rôle: {my_position}\n"
                                f"OPPOSANT DIRECT: {direct_opponent}\n"
                                f"MON ÉQUIPE: {', '.join(my_team)}\n"
                                f"ÉQUIPE ADVERSE: {', '.join(enemy_team)}\n"
                                f"MODE DE JEU: {game_mode}\n\n"
                                "INSTRUCTIONS:"
                                "1. Donne un plan de jeu global pour la partie (Win Conditions)."
                                "2. Donne les 6 items finaux à faire dans l'ordre idéal."
                                "3. Donne des conseils spécifiques pour la phase de lane contre mon opposant direct.\n"
                                "4. Formatte ta réponse EXCLUSIVEMENT en HTML (sans balises ```html ou doctype).\n\n"
                                "STRUCTURE DE RÉPONSE ATTENDUE:"
                                "<h3>🗺️ Plan de Jeu & Win Conditions</h3>"
                                "<ul><li>Stratégie...</li></ul>"
                                "<h3>⚔️ Matchup vs {direct_opponent}</h3>"
                                "<ul><li>Conseil lane...</li></ul>"
                                "<h3>📦 Build Final (6 Items)</h3>"
                                "<ol><li>Item 1</li><li>Item 2</li>...</ol>"
                            )
                        
                        # STANDARD ADVICE (> 2 minutes)
                        else:
                            print("Generating Tactical Advice...", flush=True)
                            latest_advice = get_loader_html("Analyse tactique en cours...")
                            prompt = (
                                "Tu es un coach Challenger sur League of Legends. "
                                "Ton but est de donner un avantage tactique immédiat.\n\n"
                                f"JOUEUR ACTUEL: {my_champion} (Moi)\n"
                                f"MON ÉQUIPE: {', '.join(my_team)}\n"
                                f"ÉQUIPE ADVERSE: {', '.join(enemy_team)}\n"
                                f"MODE DE JEU: {game_mode}\n"
                                f"CONTEXTE (Tes précédents conseils): {context_history}\n\n"
                                f"DONNÉES ACTUELLES DE LA PARTIE: {json.dumps(clean_data)}\n\n"
                                "INSTRUCTIONS:"
                                "1. Analyse la situation actuelle (Golds, XP, Items, KDA, Objectifs)."
                                "2. Propose un plan d'action concret pour les 2 prochaines minutes."
                                "3. Suggère les prochains items à acheter en fonction de la game."
                                "4. Sois direct, impératif et concis."
                                "5. Formatte ta réponse EXCLUSIVEMENT en HTML (sans balises ```html ou doctype).\n\n"
                                "STRUCTURE DE RÉPONSE ATTENDUE:"
                                "<h3>📊 Analyse Actuelle</h3>"
                                "<ul><li>Point clé 1</li><li>Point clé 2</li></ul>"
                                "<h3>⚡ Plan pour les 2 prochaines minutes</h3>"
                                "<ul><li><strong>Action 1</strong>: Détail...</li><li><strong>Action 2</strong>: Détail...</li></ul>"
                                "<h3>⚔️ Itemisation Recommandée</h3>"
                                "<ul><li><strong>Achat Prioritaire</strong>: Nom de l'item (Pourquoi ?)</li></ul>"
                            )
                        
                        # Debug: Save prompt and game data to file
                        if debug_mode:
                            try:
                                os.makedirs("prompt", exist_ok=True)
                                timestamp = int(time.time())
                                
                                # Save Prompt
                                with open(f"prompt/prompt_{timestamp}.txt", "w", encoding="utf-8") as f:
                                    f.write(prompt)
                                
                                # Save Game Data (JSON)
                                with open(f"prompt/game_data_{timestamp}.json", "w", encoding="utf-8") as f:
                                    json.dump(raw_data, f, indent=4)
                                    
                                print(f"DEBUG: Saved prompt and game data for timestamp {timestamp}", flush=True)
                            except Exception as e:
                                print(f"DEBUG ERROR: Could not save debug files: {e}", flush=True)
                        
                        response = model.generate_content(prompt)
                        if response.text:
                            latest_advice = response.text
                            last_gemini_call = current_time
                            advice_history.append(latest_advice)
                            last_advice_gametime = format_gametime(game_time)
                    except Exception as e:
                        print(f"Gemini Error: {e}", flush=True)
                        latest_advice = f"Erreur IA: {str(e)}"
            else:
                print(f"API returned non-200 status: {response.status_code}", flush=True)
                print(f"Response content: {response.text[:200]}", flush=True) # Print first 200 chars
                latest_advice = get_loader_html("Partie détectée. En attente de l'initialisation de l'API...")
                current_game_mode = "Unknown"
            
        except requests.exceptions.ConnectionError:
            print("Connection Error: Game probably not running or API not accessible.", flush=True)
            
            # POST-GAME ANALYSIS
            if last_valid_game_data:
                print("Game ended. Generating Post-Game Report...", flush=True)
                latest_advice = get_loader_html("Partie terminée. Génération du rapport de fin de match...")
                current_game_mode = "PostGame"
                
                try:
                    # Use FULL data (pruned but NOT filtered by time)
                    full_game_data = prune_data(last_valid_game_data)
                    
                    prompt = (
                        "Tu es un coach Challenger sur League of Legends. "
                        "La partie vient de se terminer. Fais un rapport complet.\n\n"
                        f"DONNÉES COMPLÈTES DE LA PARTIE: {json.dumps(full_game_data)}\n\n"
                        "INSTRUCTIONS:"
                        "1. Analyse la performance globale (KDA, Golds, Objectifs, Items)."
                        "2. Identifie les moments clés (Teamfights, Prises d'objectifs)."
                        "3. Donne 3 points positifs et 3 points à améliorer pour la prochaine partie."
                        "4. Formatte ta réponse EXCLUSIVEMENT en HTML (sans balises ```html ou doctype).\n\n"
                        "STRUCTURE DE RÉPONSE ATTENDUE:"
                        "<h3>🏆 Rapport de Fin de Partie</h3>"
                        "<ul><li>Résultat estimé...</li><li>Performance...</li></ul>"
                        "<h3>🔑 Moments Clés</h3>"
                        "<ul><li>Moment 1...</li><li>Moment 2...</li></ul>"
                        "<h3>📈 Axes d'Amélioration</h3>"
                        "<ul><li>Conseil 1...</li><li>Conseil 2...</li></ul>"
                    )
                    
                    response = model.generate_content(prompt)
                    if response.text:
                        latest_advice = response.text
                        last_valid_game_data = None # Reset to avoid loop
                except Exception as e:
                    print(f"Post-Game Error: {e}", flush=True)
                    latest_advice = f"Erreur Analyse Fin de Partie: {str(e)}"
                    last_valid_game_data = None
            else:
                latest_advice = get_loader_html("En attente du lancement de la partie...")
                current_game_mode = "Offline"
            pass
        except Exception as e:
            print(f"Polling Error: {e}", flush=True)
            latest_advice = f"❌ Erreur technique : {str(e)}"
            current_game_mode = "Error"
            
        # Adaptive polling strategy
        current_time = time.time()
        if model and (current_time - last_gemini_call < 110):
            # If we just called Gemini, we can sleep longer (e.g., 10s)
            # We wake up 10s before the next window to be ready
            time.sleep(10)
        else:
            # If we are close to the window or disconnected, poll faster to be responsive
            time.sleep(2)

# Start background thread
threading.Thread(target=poll_lol_api, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/advice')
def get_advice():
    return latest_advice

@app.route('/api/gamemode')
def get_gamemode():
    return current_game_mode

@app.route('/api/gametime')
def get_gametime():
    return last_advice_gametime

@app.route('/api/next-update')
def get_next_update():
    if current_game_mode in ["Offline", "Error", "PostGame"]:
        return "--"
    
    time_since_last = time.time() - last_gemini_call
    remaining = max(0, 120 - time_since_last)
    
    # If we are in early game (< 2 min), the logic is the same (120s interval)
    # If we are waiting for the first call, last_gemini_call is 0, so remaining is 0 (ready)
    
    if remaining == 0:
        return "En cours..."
        
    return f"{int(remaining)}s"

if __name__ == '__main__':
    import sys
    if "--debug" in sys.argv:
        debug_mode = True
        print("DEBUG MODE ENABLED: Prompts will be saved to ./prompt/", flush=True)
    app.run(host='0.0.0.0', port=5000)
