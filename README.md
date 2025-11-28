# Nexus Analytics

**Nexus Analytics** is a real-time League of Legends tactical assistant. It uses the local Live Client Data API to analyze your game state (Gold, XP, Items, KDA) and uses Google Gemini AI to provide immediate, challenger-level tactical advice.

## Features

*   **Real-time Analysis**: Polls game data every 2 seconds.
*   **AI Coaching**: Uses Google Gemini 2.0 Flash to generate specific advice.
*   **Context Aware**: Remembers previous advice to provide coherent coaching.
*   **Game Mode Detection**: Adapts advice for Summoner's Rift, ARAM, etc.
*   **Item Recommendations**: Suggests optimal builds based on the current game state.
*   **Hextech UI**: A beautiful, dark-themed interface inspired by the LoL client.

## Prerequisites

*   **League of Legends** installed and running.
*   **Python 3.12+** (if running manually).
*   **Google Gemini API Key** (get one from [Google AI Studio](https://aistudio.google.com/)).

## Setup & Running (Docker - Recommended)

The most reliable way to run Nexus Analytics is using Docker, as it handles network configuration automatically.

1.  **Clone the repository**.
2.  **Configure API Key**:
    *   Copy `.env.example` to `.env`.
    *   Open `.env` and paste your `GEMINI_API_KEY`.
3.  **Enable LoL API**:
    *   Go to your LoL install folder (e.g., `C:\Riot Games\League of Legends\Config`).
    *   Open `game.cfg`.
    *   Under `[General]`, add `EnableHttpApi=1`.
    *   Save and restart the game.
4.  **Launch**:
    ```bash
    docker compose up --build
    ```
    The server will start at `http://localhost:5000`.

## Running Manually (Advanced)

If you prefer to run it natively on Windows or WSL2 without Docker:

### Windows Native
Double-click **`run_on_windows.bat`**.

### WSL2 / Linux
1.  Ensure `uv` is installed.
2.  Run `uv sync`.
3.  Run `uv run app.py`.
    *   *Note*: For WSL2, you may need to configure firewall rules or use the Docker method if connection fails.

## Tech Stack

*   **Backend**: Python, Flask
*   **Frontend**: HTML, Tailwind CSS, HTMX
*   **AI**: Google Gemini 2.0 Flash
*   **Package Manager**: uv

## License

MIT
