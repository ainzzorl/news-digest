import yaml
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import os

SCOPES = "https://www.googleapis.com/auth/gmail.send"

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yml")
    with open(config_path, "r") as stream:
        try:
            print("Read config.yml")
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print("Failed to read config.yml")
            print(exc)
            exit(1)

    credentials_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "local/credentials.json")
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)
    print("Refresh token:")
    print(creds.refresh_token)
    # Save the credentials for the next run
    token_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "local/token.pickle")
    with open(token_path, "wb") as token:
        pickle.dump(creds, token)
