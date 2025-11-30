import google.generativeai as genai
import json
import time
import os
from .config import Config
from .state import state
from .utils import get_loader_html, format_gametime, prune_data

class AI:
    def __init__(self):
        self.model = None
        self.initialize_model()

    def initialize_model(self):
        if state.gemini_api_key:
            genai.configure(api_key=state.gemini_api_key)
            try:
                self.model = genai.GenerativeModel(state.gemini_model)
                print(f"Gemini model initialized: {state.gemini_model}", flush=True)
            except Exception as e:
                print(f"Error initializing Gemini model {state.gemini_model}: {e}", flush=True)
                self.model = None
        else:
            print("Error: GEMINI_API_KEY not found in environment variables.", flush=True)
            self.model = None

    def update_model(self, model_name):
        state.gemini_model = model_name
        self.initialize_model()
        return True

    def generate_advice(self, game_data, game_time, my_champion, my_position, direct_opponent, my_team, enemy_team, game_mode):
        if not self.model:
            return

        current_time = time.time()
        # Check if we should call Gemini (every 2 minutes)
        if current_time - state.last_gemini_call > Config.AI_UPDATE_INTERVAL:
            try:
                context_history = state.advice_history[-3:] if state.advice_history else "Aucun historique."
                
                # EARLY GAME STRATEGY (< 2 minutes)
                if game_time < 120:
                    print("Generating Early Game Plan...", flush=True)
                    state.latest_advice = get_loader_html("Génération du plan de jeu (Early Game)...")
                    prompt = self._create_early_game_prompt(my_champion, my_position, direct_opponent, my_team, enemy_team, game_mode)
                
                # STANDARD ADVICE (> 2 minutes)
                else:
                    print("Generating Tactical Advice...", flush=True)
                    state.latest_advice = get_loader_html("Analyse tactique en cours...")
                    prompt = self._create_tactical_prompt(my_champion, my_team, enemy_team, game_mode, context_history, game_data)

                self._save_debug_data(prompt, game_data)
                
                response = self.model.generate_content(prompt)
                if response.text:
                    state.latest_advice = response.text
                    state.last_gemini_call = current_time
                    state.advice_history.append(state.latest_advice)
                    state.last_advice_gametime = format_gametime(game_time)
            
            except Exception as e:
                print(f"Gemini Error: {e}", flush=True)
                state.latest_advice = f"Erreur IA: {str(e)}"

    def generate_post_game_report(self, full_game_data):
        if not self.model:
            return

        print("Game ended. Generating Post-Game Report...", flush=True)
        state.latest_advice = get_loader_html("Partie terminée. Génération du rapport de fin de match...")
        state.current_game_mode = "PostGame"
        
        try:
            prompt = self._create_post_game_prompt(full_game_data)
            response = self.model.generate_content(prompt)
            if response.text:
                state.latest_advice = response.text
                state.last_valid_game_data = None # Reset to avoid loop
        except Exception as e:
            print(f"Post-Game Error: {e}", flush=True)
            state.latest_advice = f"Erreur Analyse Fin de Partie: {str(e)}"
            state.last_valid_game_data = None

    def _create_early_game_prompt(self, my_champion, my_position, direct_opponent, my_team, enemy_team, game_mode):
        return (
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

    def _create_tactical_prompt(self, my_champion, my_team, enemy_team, game_mode, context_history, game_data):
        return (
            "Tu es un coach Challenger sur League of Legends. "
            "Ton but est de donner un avantage tactique immédiat.\n\n"
            f"JOUEUR ACTUEL: {my_champion} (Moi)\n"
            f"MON ÉQUIPE: {', '.join(my_team)}\n"
            f"ÉQUIPE ADVERSE: {', '.join(enemy_team)}\n"
            f"MODE DE JEU: {game_mode}\n"
            f"CONTEXTE (Tes précédents conseils): {context_history}\n\n"
            f"DONNÉES ACTUELLES DE LA PARTIE: {json.dumps(game_data)}\n\n"
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

    def _create_post_game_prompt(self, full_game_data):
        return (
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

    def _save_debug_data(self, prompt, game_data):
        if state.debug_mode:
            try:
                os.makedirs("prompt", exist_ok=True)
                timestamp = int(time.time())
                
                with open(f"prompt/prompt_{timestamp}.txt", "w", encoding="utf-8") as f:
                    f.write(prompt)
                
                with open(f"prompt/game_data_{timestamp}.json", "w", encoding="utf-8") as f:
                    json.dump(game_data, f, indent=4)
                    
                print(f"DEBUG: Saved prompt and game data for timestamp {timestamp}", flush=True)
            except Exception as e:
                print(f"DEBUG ERROR: Could not save debug files: {e}", flush=True)

# Singleton
ai = AI()
