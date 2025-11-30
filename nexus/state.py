from .utils import get_loader_html

class GameState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GameState, cls).__new__(cls)
            cls._instance.reset()
        return cls._instance

    def reset(self):
        self.latest_advice = get_loader_html("En attente du lien neural avec la Faille de l'invocateur...")
        self.last_gemini_call = 0
        self.advice_history = []
        self.current_game_mode = "Unknown"
        self.last_advice_gametime = "00:00"
        self.debug_mode = False
        self.last_valid_game_data = None
        
        # Mutable Settings
        from .config import Config
        self.gemini_model = Config.GEMINI_MODEL
        self.gemini_api_key = Config.GEMINI_API_KEY

# Singleton instance
state = GameState()
