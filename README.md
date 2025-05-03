# News Digest

A Python-based news aggregation and distribution system that collects news from various sources and delivers them through different channels.

## Features

- RSS feed parsing
- Reddit integration
- Google API integration
- Telegram integration
- AWS integration
- Configurable through YAML

## Setup

1. Install Python 3.13 or higher
2. Install Poetry for dependency management:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```
3. Install project dependencies:
   ```bash
   poetry install
   ```

## Configuration

The project uses `config.yml` for configuration. Make sure to set up the necessary API keys and credentials for:

- Google APIs
- Reddit API
- Telegram API
- AWS credentials

## Usage

The project is structured into several components:

- `scripts/`: Contains the main scripts for news collection and distribution
- `package/`: Core package functionality

## License

This project is private and proprietary.
