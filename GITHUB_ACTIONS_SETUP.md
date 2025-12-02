# GitHub Actions Setup Guide

## Problem: Dispenser Blocked by GitHub

GitHub Actions IP addresses are often blocked by the AuroraOSS dispenser, resulting in 403 Forbidden errors.

## Solutions

### Option 1: Use Manual Auth Token (Recommended)

1. **Get auth token locally:**
   ```bash
   # On your local machine (not GitHub Actions)
   ./gplay auth --max-attempts 20
   ```

2. **Copy the token:**
   ```bash
   cat ~/.gplay-auth.json
   ```

3. **Add as GitHub Secret:**
   - Go to your repository → Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `GPLAY_AUTH_TOKEN`
   - Value: Paste the entire content of `~/.gplay-auth.json`
   - Click "Add secret"

4. **Run the workflow:**
   - The workflow will automatically use your token
   - Token is valid for several weeks/months

### Option 2: Use Tor Proxy (Experimental)

The workflow includes an option to use Tor proxy to bypass IP blocks:

1. When running the workflow, set "Try using proxy" to `true`
2. This will route authentication through Tor network
3. May be slower but can bypass IP blocks

**Note:** Tor support requires `pysocks` package (already in requirements.txt)

### Option 3: Self-Hosted Runner

If you have a server/VPS that's not blocked:

1. Set up a [self-hosted GitHub Actions runner](https://docs.github.com/en/actions/hosting-your-own-runners)
2. Modify the workflow to use your runner:
   ```yaml
   runs-on: self-hosted  # instead of ubuntu-latest
   ```

## Token Expiration

Auth tokens eventually expire. When you see authentication errors:

1. Generate a new token locally: `./gplay auth --max-attempts 20`
2. Update the `GPLAY_AUTH_TOKEN` secret in GitHub

## Testing Locally

Before using GitHub Actions, test locally:

```bash
# Authenticate
./gplay auth --max-attempts 20

# Test download
./gplay download com.whatsapp -m -a arm64

# If successful, the same token will work in GitHub Actions
```

## Troubleshooting

### "Authentication failed" in GitHub Actions

1. Check if `GPLAY_AUTH_TOKEN` secret is set correctly
2. Verify token is valid by testing locally
3. Try regenerating the token

### "Token validation failed"

The token might be expired or invalid:
1. Generate a fresh token locally
2. Update the GitHub secret

### Proxy not working

If Tor proxy fails:
1. Disable proxy option (set to `false`)
2. Use manual token instead (Option 1)

---

## Quick Start

**Easiest way to get started:**

```bash
# 1. On your local machine
./gplay auth --max-attempts 20

# 2. Copy token
cat ~/.gplay-auth.json

# 3. Add to GitHub Secrets as GPLAY_AUTH_TOKEN

# 4. Run workflow - it will use your token automatically
```

That's it! No need to deal with dispenser blocks in GitHub Actions.
