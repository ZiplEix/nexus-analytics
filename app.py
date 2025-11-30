from flask import Flask, render_template, request
import threading
import time
import sys
from nexus.state import state
from nexus.watcher import poll_lol_api
from nexus.config import Config
from nexus.ai import ai

app = Flask(__name__)

# Start background thread
threading.Thread(target=poll_lol_api, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        model_name = request.form.get('model')
        debug_mode = request.form.get('debug') == 'on'

        print(f"Updating settings: model={model_name}, debug={debug_mode}", flush=True)
        
        # Update State
        state.debug_mode = debug_mode
        
        # Update AI Model
        if model_name and model_name != state.gemini_model:
            ai.update_model(model_name)
            
        return '<span class="text-green-400">Paramètres sauvegardés !</span>'
    
    return render_template('settings.html', current_model=state.gemini_model, debug_mode=state.debug_mode)

@app.route('/api/advice')
def get_advice():
    return state.latest_advice

@app.route('/api/gamemode')
def get_gamemode():
    return state.current_game_mode

@app.route('/api/gametime')
def get_gametime():
    return state.last_advice_gametime

@app.route('/api/next-update')
def get_next_update():
    if state.current_game_mode in ["Offline", "Error", "PostGame"]:
        return "--"
    
    time_since_last = time.time() - state.last_gemini_call
    remaining = max(0, Config.AI_UPDATE_INTERVAL - time_since_last)
    
    if remaining == 0:
        return "En cours..."
        
    return f"{int(remaining)}s"

if __name__ == '__main__':
    if "--debug" in sys.argv:
        state.debug_mode = True
        print("DEBUG MODE ENABLED: Prompts will be saved to ./prompt/", flush=True)
    app.run(host='0.0.0.0', port=5000)
