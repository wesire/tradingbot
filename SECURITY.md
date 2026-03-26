# Security Policy

## ⚠️ Never Share Your `.env` File

Your `.env` file contains live API keys and secrets. **Never** share its contents publicly — not in GitHub issues, pull requests, chat messages, screenshots, or anywhere else.

If you have accidentally exposed your `.env` file contents, treat **all credentials in it as compromised** and rotate them immediately (see below).

---

## Ensuring `.env` Is Always Ignored by Git

The `.gitignore` in this repository already includes `.env`. To verify:

```bash
grep '\.env' .gitignore
```

You should see `.env` listed. If you ever add a new secrets file, add it to `.gitignore` before creating it:

```bash
echo "my-secrets-file" >> .gitignore
```

**Never run `git add .env`** or force-add it with `-f`.

---

## How to Rotate Compromised API Keys

If any of the following keys were exposed, rotate them immediately using the steps below.

### Binance (`EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET`)

1. Log in to [https://www.binance.com](https://www.binance.com)
2. Go to **Profile → API Management**
3. Delete the compromised API key
4. Create a new API key with only the permissions you need (e.g., Futures Trading — avoid Withdrawals unless required)
5. Update your `.env` with the new key and secret

### OpenAI (`OPENAI_API_KEY`)

1. Log in to [https://platform.openai.com](https://platform.openai.com)
2. Go to **API keys** in the left sidebar
3. Click **Revoke** next to the exposed key
4. Click **+ Create new secret key** and give it a descriptive name
5. Update your `.env` with the new key
6. Check your [Usage page](https://platform.openai.com/usage) for any unexpected charges

### CryptoPanic (`CRYPTOPANIC_API_KEY`)

1. Log in to [https://cryptopanic.com](https://cryptopanic.com)
2. Go to **Account → API**
3. Regenerate your API token
4. Update your `.env` with the new token

### Bybit (`BYBIT_API_KEY` / `BYBIT_API_SECRET`)

1. Log in to [https://www.bybit.com](https://www.bybit.com)
2. Go to **Account & Security → API Management** (or visit [https://www.bybit.com/app/user/api-management](https://www.bybit.com/app/user/api-management))
3. Delete the compromised API key
4. Create a new key with the minimum required permissions
5. Update your `.env` with the new key and secret

---

## Using Environment Variables and Secret Managers in Production

For production deployments, avoid storing secrets in a `.env` file on disk. Instead, use one of the following approaches:

### Docker / Docker Compose

Pass secrets directly as environment variables at runtime:

```bash
docker run -e EXCHANGE_API_KEY=<key> -e EXCHANGE_API_SECRET=<secret> ...
```

Or use Docker Secrets for Swarm deployments.

### Cloud Secret Managers

| Provider | Service |
|---|---|
| AWS | Secrets Manager / Parameter Store |
| GCP | Secret Manager |
| Azure | Key Vault |
| HashiCorp | Vault |

Load secrets at container startup using the cloud provider's SDK or a sidecar, rather than writing them to disk.

### CI/CD Pipelines

Store secrets as **encrypted environment variables** or **repository secrets** in your CI/CD system (e.g., GitHub Actions Secrets, GitLab CI Variables). Never hard-code them in workflow files.

---

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please open a GitHub issue marked **[SECURITY]** or contact the repository owner directly. Do not disclose vulnerabilities publicly before they have been addressed.
