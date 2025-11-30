import os

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
