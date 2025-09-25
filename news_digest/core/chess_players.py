import os
import time
from datetime import datetime
import re
import logging
import json
from typing import Dict, List, Optional, Any

import requests
import boto3
from botocore.exceptions import ClientError

from news_digest.utils.util import is_running_in_lambda


def gen_chess_players_digest(
    config: Dict[str, Any],
    source_options: Optional[Dict[str, Any]] = None,
    global_config: Optional[Dict[str, Any]] = None,
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

    s3_config = global_config.get("s3") if global_config else None
    players = config["players"]

    # Load all processed games from S3 in a single operation
    all_processed_games, s3_object_age = (
        load_all_processed_games_from_s3(s3_config) if s3_config else ({}, None)
    )

    # Track all current games for batch S3 update
    all_current_games = {}

    for player in players:
        try:
            processed_game_ids = all_processed_games.get(player, [])
            player_digest, current_game_ids = _gen_player_digest(
                config, player, processed_game_ids, s3_object_age
            )
            res += player_digest

            # Store current game IDs for batch update
            if current_game_ids:
                # Combine existing processed IDs with new ones
                all_processed_ids = list(set(processed_game_ids + current_game_ids))
                all_current_games[player] = all_processed_ids

        except Exception as e:
            error_msg = f"Failed to process player {player}: {str(e)}"
            print(f"ERROR: {error_msg}")
            logging.error(error_msg, exc_info=True)
            errors.append(error_msg)
            # Add error info to the result
            res += f"<h3>{player}</h3>"
            res += f"<p><em>Error: Unable to fetch player data - {str(e)}</em></p>"

    # Save all processed games to S3 in a single batch operation
    if s3_config and all_current_games:
        save_all_processed_games_to_s3(all_current_games, s3_config)

    # Add error summary if there were any errors
    if errors:
        res += "<h4>Processing Errors</h4>"
        res += "<ul>"
        for error in errors:
            res += f"<li>{error}</li>"
        res += "</ul>"

    return res


def _has_new_ratings(
    rating_history: Optional[List[Dict[str, Any]]], s3_object_age: Optional[datetime]
) -> bool:
    """
    Check if there are new ratings since the last S3 object update.

    Args:
        rating_history: Rating history from Chess Tools API
        s3_object_age: Last modified date of S3 object

    Returns:
        bool: True if there are new ratings, False otherwise
    """
    if not rating_history or not s3_object_age:
        return False

    # Check if the most recent rating period is newer than the S3 object
    if len(rating_history) > 0:
        latest_period = rating_history[0]
        latest_date_str = latest_period.get("date", "")

        if latest_date_str:
            try:
                # Parse the date from format "2025-09" to datetime
                from datetime import datetime, timezone

                latest_date = datetime.strptime(latest_date_str, "%Y-%m")

                # Make both datetimes timezone-aware for comparison
                # Assume the rating date is in UTC (since FIDE ratings are typically published in UTC)
                latest_date = latest_date.replace(tzinfo=timezone.utc)

                # If s3_object_age is timezone-naive, assume it's UTC
                if s3_object_age.tzinfo is None:
                    s3_object_age = s3_object_age.replace(tzinfo=timezone.utc)

                # Compare with S3 object age
                return latest_date > s3_object_age
            except ValueError:
                # If we can't parse the date, assume it's new
                return True

    return False


def _gen_player_digest(
    config: Dict[str, Any],
    player: str,
    processed_game_ids: List[str],
    s3_object_age: Optional[datetime],
) -> tuple[str, List[str]]:
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

    # Add recent games
    recent_games_count = config.get(
        "recent_games_count", 5
    )  # Default to 5 if not specified
    games = _extract_recent_games(player_info_html, player, recent_games_count)

    current_game_ids = []
    new_games = []

    if games:
        # Extract IDs for all current games
        current_game_ids = [
            game.get("game_id") for game in games if game.get("game_id")
        ]

        # Filter out games that have already been processed
        new_games = filter_new_games(games, processed_game_ids)

    # Check if there are new ratings
    has_new_ratings = _has_new_ratings(rating_history, s3_object_age)

    # If no new games and no new ratings, return empty string
    if not new_games and not has_new_ratings:
        return "", current_game_ids

    # Build the digest content
    res = f"<h3>{player}</h3>"

    # Display current ratings and recent changes
    res += _format_ratings_section(ratings, rating_history)

    # Only display new games that haven't been reported before
    if new_games:
        res += f"<h4>Recent Games ({len(new_games)} new)</h4>"
        res += "<ul>"
        for i, game in enumerate(new_games, 1):
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

    return res, current_game_ids


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

            # Extract game ID from the result cell's href attribute
            game_id = None
            result_link = cells[4].find("a")
            if result_link and result_link.get("href"):
                href = result_link.get("href")
                # Extract gid parameter from URLs like "/game.php?gid=4572033"
                gid_match = re.search(r"gid=(\d+)", href)
                if gid_match:
                    game_id = gid_match.group(1)

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
                    "game_id": game_id,
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


def filter_new_games(
    games: List[Dict[str, str]], processed_game_ids: List[str]
) -> List[Dict[str, str]]:
    """
    Filter out games that have already been processed.

    Args:
        games: List of game dictionaries
        processed_game_ids: List of already processed game IDs

    Returns:
        List of new games that haven't been processed yet
    """
    new_games = []
    for game in games:
        game_id = game.get("game_id")
        if game_id and game_id not in processed_game_ids:
            new_games.append(game)

    return new_games


def get_s3_all_processed_games_key() -> str:
    """
    Generate S3 key for storing all processed games in a single object.

    Returns:
        str: S3 key path for the consolidated games file
    """
    return "chess_processed_games/all_processed_games.json"


def load_all_processed_games_from_s3(
    s3_config: Dict[str, str],
) -> tuple[Dict[str, List[str]], Optional[datetime]]:
    """
    Load all processed game IDs from a single S3 object.

    Args:
        s3_config: S3 configuration with bucket and region

    Returns:
        Tuple of (Dictionary mapping player names to their processed game IDs, S3 object last modified date)
    """
    if not s3_config:
        return {}, None

    s3_key = get_s3_all_processed_games_key()

    try:
        s3 = boto3.client("s3", region_name=s3_config.get("region"))
        response = s3.get_object(Bucket=s3_config["bucket"], Key=s3_key)
        content = response["Body"].read().decode("utf-8")
        data = json.loads(content)

        # Get the last modified date from S3 response metadata
        last_modified = response.get("LastModified")
        if last_modified:
            # Convert to datetime if it's not already
            if isinstance(last_modified, str):
                last_modified = datetime.fromisoformat(
                    last_modified.replace("Z", "+00:00")
                )
            elif hasattr(last_modified, "replace"):
                # It's already a datetime object
                pass
            else:
                last_modified = None

        # Return the players data, defaulting to empty dict if not found
        return data.get("players", {}), last_modified

    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            # File doesn't exist yet, return empty dict
            print("No processed games file found in S3, starting fresh")
            return {}, None
        else:
            print(f"ERROR: Failed to load processed games from S3: {str(e)}")
            return {}, None
    except Exception as e:
        print(f"ERROR: Failed to parse processed games from S3: {str(e)}")
        return {}, None


def save_all_processed_games_to_s3(
    player_games_data: Dict[str, List[str]], s3_config: Dict[str, str]
) -> bool:
    """
    Save all processed game IDs to a single S3 object.

    Args:
        player_games_data: Dictionary mapping player names to their processed game IDs
        s3_config: S3 configuration with bucket and region

    Returns:
        bool: True if successful, False otherwise
    """
    if not s3_config:
        print("WARNING: No S3 config provided, skipping save")
        return False

    if not player_games_data:
        print("WARNING: No player data provided, skipping save")
        return False

    s3_key = get_s3_all_processed_games_key()

    try:
        s3 = boto3.client("s3", region_name=s3_config.get("region"))

        # Prepare consolidated data structure
        data = {
            "last_updated": datetime.now().isoformat(),
            "total_players": len(player_games_data),
            "total_games": sum(len(ids) for ids in player_games_data.values()),
            "players": player_games_data,
        }

        # Upload to S3
        s3.put_object(
            Bucket=s3_config["bucket"],
            Key=s3_key,
            Body=json.dumps(data, indent=2),
            ContentType="application/json",
        )

        print(
            f"Successfully saved processed games for {data['total_players']} players "
            f"({data['total_games']} total game IDs) to single S3 object"
        )
        return True

    except Exception as e:
        print(f"ERROR: Failed to save processed games to S3: {str(e)}")
        return False
