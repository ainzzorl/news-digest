import yaml
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = "https://www.googleapis.com/auth/gmail.send"

if __name__ == "__main__":
    with open("config.yml", "r") as stream:
        try:
            print("Read config.yml")
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print("Failed to read config.yml")
            print(exc)
            exit(1)

    flow = InstalledAppFlow.from_client_secrets_file("local/credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)
    print("Refresh token:")
    print(creds.refresh_token)
    # Save the credentials for the next run
    with open("local/token.pickle", "wb") as token:
        pickle.dump(creds, token)
