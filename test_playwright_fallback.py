#!/usr/bin/env python3
"""
Test script to verify Playwright with fallback to requests functionality.
This script tests the chess player info fetching with both methods.
"""

import sys
import os
import asyncio

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_digest.core.chess_players import _get_player_info


async def test_player_fetch(player_name: str):
    """Test fetching player info with Playwright and fallback."""
    print(f"\n{'='*60}")
    print(f"Testing fetch for player: {player_name}")
    print(f"{'='*60}")

    try:
        html_content = await _get_player_info(player_name)
        print(f"✓ Successfully fetched player info")
        print(f"  Content length: {len(html_content)} characters")

        # Basic validation
        if "365chess" in html_content.lower():
            print(f"  ✓ Content appears to be from 365chess.com")
        else:
            print(f"  ⚠ Content might not be from 365chess.com")

        return True
    except Exception as e:
        print(f"✗ Failed to fetch player info: {str(e)}")
        return False


async def main():
    """Main test function."""
    print("\n" + "=" * 60)
    print("Chess Player Info Fetch Test")
    print("=" * 60)
    print("\nThis script tests:")
    print("  1. Playwright fetch (primary method)")
    print("  2. Requests fallback (if Playwright fails)")
    print("  3. Local cache (in non-production mode)")
    print("\n")

    # Test with a well-known player
    test_players = [
        "Magnus_Carlsen",
    ]

    success_count = 0
    total_count = len(test_players)

    for player in test_players:
        if await test_player_fetch(player):
            success_count += 1

    print(f"\n{'='*60}")
    print(f"Test Results: {success_count}/{total_count} successful")
    print(f"{'='*60}\n")

    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
