## Security & Secrets

Do NOT commit secrets (client IDs, client secrets, refresh tokens) to this repository.

- Use GitHub Secrets for CI/CD workflows (already configured in this repo).
- Keep local credentials in a file named `.env` or `.env.local` and never commit it.
- This repository already ignores `.env` and common secret files via `.gitignore`.

To create a local copy for development, add a file named `.env` to the project root with the following keys (example values omitted):

```
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
SPOTIPY_REFRESH_TOKEN=your_refresh_token_here
```

If you accidentally commit a secret, rotate it immediately (revoke the secret in the provider) and remove it from the git history.
