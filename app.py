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
    model = genai.GenerativeModel('gemini-2.0-flash')
else:
    print("WARNING: GEMINI_API_KEY not found in environment variables.")
    model = None

app = Flask(__name__)

# Global state
latest_advice = "En attente du lien neural avec la Faille de l'invocateur..."
last_gemini_call = 0
advice_history = []
current_game_mode = "Unknown"

def prune_data(data):
    """
    Recursively removes 'itemDesc', 'perks', 'abilities', 'skins' from the JSON data
    to save tokens.
    """
    if isinstance(data, dict):
        return {
            k: prune_data(v) 
            for k, v in data.items() 
            if k not in ['itemDesc', 'perks', 'abilities', 'skins']
        }
    elif isinstance(data, list):
        return [prune_data(i) for i in data]
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
    global latest_advice, last_gemini_call, advice_history, current_game_mode
    
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
                clean_data = prune_data(raw_data)
                
                # Extract Game Mode
                game_mode = raw_data.get('gameData', {}).get('gameMode', 'UNKNOWN')
                current_game_mode = game_mode
                
                # Check if we should call Gemini (every 2 minutes)
                current_time = time.time()
                if model and (current_time - last_gemini_call > 120):
                    try:
                        # Keep only last 3 advices for context
                        context_history = advice_history[-3:] if advice_history else "Aucun historique."
                        
                        prompt = (
                            "Tu es un coach Challenger sur League of Legends. "
                            "Ton but est de donner un avantage tactique immédiat.\n\n"
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
                        
                        response = model.generate_content(prompt)
                        if response.text:
                            latest_advice = response.text
                            last_gemini_call = current_time
                            advice_history.append(latest_advice)
                    except Exception as e:
                        print(f"Gemini Error: {e}", flush=True)
                        latest_advice = f"Erreur IA: {str(e)}"
            else:
                print(f"API returned non-200 status: {response.status_code}", flush=True)
                print(f"Response content: {response.text[:200]}", flush=True) # Print first 200 chars
                latest_advice = "⚠️ Partie non détectée ou API indisponible. Assurez-vous d'être en jeu."
                current_game_mode = "Unknown"
            
        except requests.exceptions.ConnectionError:
            print("Connection Error: Game probably not running or API not accessible.", flush=True)
            latest_advice = "⏳ En attente du lancement de la partie..."
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
