import os
import time
import feedparser
from datetime import datetime
from time import mktime
import re
import logging
from typing import Dict, List, Optional, Any, Union

import requests

from news_digest.utils.util import *


def gen_chess_players_digest(
    config: Dict[str, Any], source_options: Optional[Dict[str, Any]] = None
) -> str:
    res = ""
    res += "<h2>Chess Players</h2>"
    errors = []

    current_day = datetime.now().weekday() + 1
    if current_day not in config["days"]:
        print(
            f'Skipping {config["name"]}, not in days {config["days"]}. Current day: {current_day}'
        )
        return ""

    for player in config["players"]:
        try:
            player_digest = _gen_player_digest(config, player)
            res += player_digest
        except Exception as e:
            error_msg = f"Failed to process player {player}: {str(e)}"
            print(f"ERROR: {error_msg}")
            logging.error(error_msg, exc_info=True)
            errors.append(error_msg)
            # Add error info to the result
            res += f"<h3>{player}</h3>"
            res += f"<p><em>Error: Unable to fetch player data - {str(e)}</em></p>"

    # Add error summary if there were any errors
    if errors:
        res += "<h4>Processing Errors</h4>"
        res += "<ul>"
        for error in errors:
            res += f"<li>{error}</li>"
        res += "</ul>"

    return res


def _gen_player_digest(config: Dict[str, Any], player: str) -> str:
    res = f"<h3>{player}</h3>"

    # Query 365chess.com
    # First, check if local/365chess/<player> exists
    # If no, fetch it from https://www.365chess.com/players/<player>
    # Save it to local/365chess/<player>

    player_info_html = _get_player_info(player)

    # Extract player information
    ratings = _extract_chess_ratings(player_info_html)
    fide_id = _extract_fide_id(player_info_html)

    # Try to get rating history from Chess Tools API if we have FIDE ID
    rating_history = None
    if fide_id:
        try:
            rating_history = _get_rating_history(fide_id)
        except Exception as e:
            print(
                f"WARNING: Failed to fetch rating history for {player} (FIDE ID: {fide_id}): {str(e)}"
            )

    # Display current ratings and recent changes
    res += _format_ratings_section(ratings, rating_history)

    # Add recent games
    recent_games_count = config.get(
        "recent_games_count", 5
    )  # Default to 5 if not specified
    games = _extract_recent_games(player_info_html, player, recent_games_count)
    if games:
        res += f"<h4>Recent Games ({len(games)})</h4>"
        res += "<ul>"
        for i, game in enumerate(games, 1):
            # Format the result for better display
            result_display = (
                game["result"]
                .replace("½-½", "½-½")
                .replace("1-0", "1-0")
                .replace("0-1", "0-1")
            )

            # Display white vs black players
            matchup = f"{game['white_player']} ({game['white_rating']}) vs {game['black_player']} ({game['black_rating']})"

            res += f"<li><strong>{i}.</strong> {matchup} "
            res += f"- <strong>{result_display}</strong> "
            res += f"<em>{game['tournament']}</em> "
            res += f"({game['date']})</li>"
        res += "</ul>"

    return res


def _extract_fide_id(html_content: str) -> Optional[str]:
    """
    Extract FIDE ID from 365chess.com HTML.

    Args:
        html_content: HTML content from 365chess.com player page

    Returns:
        str: FIDE ID if found, None otherwise
    """
    if not html_content or not isinstance(html_content, str):
        raise ValueError("Invalid HTML content provided")

    # Look for FIDE ID pattern: <td>XXXXXXX <a href="https://ratings.fide.com/profile/XXXXXXX"
    fide_match = re.search(
        r'<td>(\d+)\s*<a href="https://ratings\.fide\.com/profile/\d+"',
        html_content,
        re.IGNORECASE,
    )

    return fide_match.group(1) if fide_match else None


def _extract_chess_ratings(html_content: str) -> Dict[str, Optional[int]]:
    """
    Extract classic, rapid, and blitz ratings from 365chess.com HTML.

    Returns:
        dict: {'classic': int, 'rapid': int, 'blitz': int} or None for missing ratings
    """
    if not html_content or not isinstance(html_content, str):
        raise ValueError("Invalid HTML content provided")

    ratings = {}

    # Extract Classic rating
    classic_match = re.search(
        r"<strong>ELO Classic:</strong></td>\s*<td>(\d+)</td>",
        html_content,
        re.IGNORECASE,
    )
    ratings["classic"] = int(classic_match.group(1)) if classic_match else None

    # Extract Rapid rating
    rapid_match = re.search(
        r"<strong>ELO Rapid:</strong></td>\s*<td>(\d+)</td>",
        html_content,
        re.IGNORECASE,
    )
    ratings["rapid"] = int(rapid_match.group(1)) if rapid_match else None

    # Extract Blitz rating
    blitz_match = re.search(
        r"<strong>ELO Blitz:</strong></td>\s*<td>(\d+)</td>",
        html_content,
        re.IGNORECASE,
    )
    ratings["blitz"] = int(blitz_match.group(1)) if blitz_match else None

    return ratings


def _extract_recent_games(
    html_content: str, player_name: str, num_games: int = 5
) -> List[Dict[str, str]]:
    """
    Extract recent games from 365chess.com HTML content.

    Args:
        html_content: HTML content from 365chess.com player page
        player_name: Name of the player to extract games for
        num_games: Number of recent games to extract (default: 5)

    Returns:
        list: List of dictionaries containing game information
    """
    if not html_content or not isinstance(html_content, str):
        raise ValueError("Invalid HTML content provided")

    if not player_name or not isinstance(player_name, str):
        raise ValueError("Invalid player name provided")

    import re
    from bs4 import BeautifulSoup

    games = []

    # Find the games table - look for the table that contains game data
    soup = BeautifulSoup(html_content, "html.parser")

    # Find the table that has headers for White, Black, Result, etc.
    games_table = None
    for table in soup.find_all("table", class_="table stable"):
        thead = table.find("thead")
        if thead:
            header_text = thead.get_text()
            if (
                "White" in header_text
                and "Black" in header_text
                and "Result" in header_text
            ):
                games_table = table
                break

    if not games_table:
        print(f"WARNING: No games table found for {player_name}")
        return games

    # Find all game rows
    tbody = games_table.find("tbody")
    if not tbody:
        print(f"WARNING: No table body found for {player_name}")
        return games

    game_rows = tbody.find_all("tr", class_=["light", "dark"])

    for row_idx, row in enumerate(
        game_rows[:num_games]
    ):  # Limit to requested number of games
        cells = row.find_all("td")
        if len(cells) >= 8:  # Ensure we have enough columns
            # Extract game data
            white_player = cells[0].get_text(strip=True) or "Unknown"
            white_rating = cells[1].get_text(strip=True) or "?"
            black_player = cells[2].get_text(strip=True) or "Unknown"
            black_rating = cells[3].get_text(strip=True) or "?"
            result_cell = cells[4].get_text(strip=True) or "Unknown"
            moves = cells[5].get_text(strip=True) or "?"
            eco = cells[6].get_text(strip=True) or "?"
            date = cells[7].get_text(strip=True) or "Unknown"
            tournament = cells[8].get_text(strip=True) if len(cells) > 8 else "Unknown"

            # Clean up the result (remove extra text and images)
            result = result_cell.split()[0] if result_cell else "Unknown"

            # Store white and black player information directly
            games.append(
                {
                    "white_player": white_player,
                    "white_rating": white_rating,
                    "black_player": black_player,
                    "black_rating": black_rating,
                    "result": result,
                    "date": date,
                    "tournament": tournament,
                    "moves": moves,
                    "eco": eco,
                }
            )

    return games


def _get_player_info(player: str) -> str:
    sanitized_player = player.replace(" ", "_")

    # Try to read from local cache first
    if not is_running_in_lambda() and os.path.exists(
        f"local/365chess/{sanitized_player}"
    ):
        print(f"Reading {player} from local/365chess/{sanitized_player}")
        with open(f"local/365chess/{sanitized_player}", "r", encoding="utf-8") as f:
            return f.read()

    url = f"https://www.365chess.com/players/{sanitized_player}"
    print(f"Fetching {player} from {url}")

    # Add timeout and better error handling
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    # Check if we got a valid response
    if not response.text or len(response.text) < 100:
        raise Exception(f"Received empty or very short response for {player}")

    time.sleep(1)  # Rate limiting

    # Try to save to local cache
    if not is_running_in_lambda():
        # Ensure directory exists
        os.makedirs("local/365chess", exist_ok=True)
        with open(f"local/365chess/{sanitized_player}", "w", encoding="utf-8") as f:
            f.write(response.text)

    return response.text


def _get_rating_history(fide_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch player rating history from Chess Tools API.

    Args:
        fide_id: FIDE ID of the player

    Returns:
        list: List of rating history entries or None if failed
    """
    import json

    # Try to read from local cache first
    cache_file = f"local/rating_api/{fide_id}"
    if not is_running_in_lambda() and os.path.exists(cache_file):
        print(f"Reading rating history for FIDE ID {fide_id} from {cache_file}")
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                return cached_data if isinstance(cached_data, list) else None
        except (json.JSONDecodeError, IOError) as e:
            print(f"WARNING: Failed to read cache file {cache_file}: {str(e)}")
            # Continue to fetch from API if cache read fails

    url = f"https://api.chesstools.org/fide/player_history/?fide_id={fide_id}"
    print(f"Fetching rating history from {url}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                # Try to save to local cache
                if not is_running_in_lambda():
                    try:
                        # Ensure directory exists
                        os.makedirs("local/rating_api", exist_ok=True)
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                        print(
                            f"Saved rating history for FIDE ID {fide_id} to {cache_file}"
                        )
                    except IOError as e:
                        print(
                            f"WARNING: Failed to save cache file {cache_file}: {str(e)}"
                        )

                return data
            else:
                return None
        else:
            print(
                f"WARNING: Unexpected status code {response.status_code} from Chess Tools API"
            )
            return None

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to fetch rating history: {str(e)}")
        return None
    except ValueError as e:
        print(f"ERROR: Failed to parse JSON response: {str(e)}")
        return None


def _format_ratings_section(
    ratings: Dict[str, Optional[int]], rating_history: Optional[List[Dict[str, Any]]]
) -> str:
    """
    Format the ratings section with current ratings and recent changes.

    Args:
        ratings: Current ratings from 365chess.com
        rating_history: Rating history from Chess Tools API

    Returns:
        str: HTML formatted ratings section
    """
    result = ""

    # Display current ratings from 365chess (fallback to Chess Tools if needed)
    current_ratings = {}
    if rating_history and len(rating_history) > 0:
        # Get most recent ratings from API
        latest = rating_history[0]
        current_ratings = {
            "classic": latest.get("classical_rating"),
            "rapid": latest.get("rapid_rating"),
            "blitz": latest.get("blitz_rating"),
        }

    # Use 365chess ratings if available, otherwise use API ratings
    display_ratings = {}
    for time_control in ["classic", "rapid", "blitz"]:
        if ratings.get(time_control):
            display_ratings[time_control] = ratings[time_control]
        elif current_ratings.get(time_control):
            display_ratings[time_control] = current_ratings[time_control]

    # Format current ratings
    ratings_list = []
    if display_ratings.get("classic"):
        ratings_list.append(f"Classic: {display_ratings['classic']}")
    if display_ratings.get("rapid"):
        ratings_list.append(f"Rapid: {display_ratings['rapid']}")
    if display_ratings.get("blitz"):
        ratings_list.append(f"Blitz: {display_ratings['blitz']}")

    if ratings_list:
        result += (
            "<p><strong>Current Ratings:</strong> " + " | ".join(ratings_list) + "</p>"
        )

    # Add rating changes if we have history
    if rating_history and len(rating_history) >= 2:
        result += _format_rating_changes(rating_history)

    return result


def _format_rating_changes(rating_history: List[Dict[str, Any]]) -> str:
    """
    Format rating changes from the most recent periods.

    Args:
        rating_history: List of rating history entries

    Returns:
        str: HTML formatted rating changes
    """
    if len(rating_history) < 2:
        return ""

    current = rating_history[0]
    previous = rating_history[1]

    changes = []

    # Calculate changes for each time control
    for time_control, api_field in [
        ("Classic", "classical_rating"),
        ("Rapid", "rapid_rating"),
        ("Blitz", "blitz_rating"),
    ]:
        current_rating = current.get(api_field)
        previous_rating = previous.get(api_field)

        if current_rating and previous_rating:
            change = current_rating - previous_rating
            if change != 0:
                sign = "+" if change > 0 else ""
                changes.append(f"{time_control}: {sign}{change}")

    if changes:
        period_info = f"({previous.get('period', 'Previous')} → {current.get('period', 'Current')})"
        return f"<p><strong>Recent Changes:</strong> {' | '.join(changes)} {period_info}</p>"

    return ""
