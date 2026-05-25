# Analytics (Umami)

Self-hosted privacy-friendly web analytics at https://monet.dmfenton.net/analytics/

## Architecture

- **Umami**: Analytics dashboard and API (port 3000 internal)
- **PostgreSQL**: Stores analytics data (separate from app SQLite)
- **Tracking**: Lightweight script (~1KB) in web frontend

## First-Time Setup

After deploying for the first time:

1. **Access Umami dashboard**: https://monet.dmfenton.net/analytics/
2. **Login** with default credentials: `admin` / `umami`
3. **Change the admin password** immediately
4. **Add a website**:
   - Go to Settings -> Websites -> Add website
   - Name: `Code Monet`
   - Domain: `monet.dmfenton.net`
   - Click Save
5. **Copy the Website ID** (UUID shown after creating)
6. **Add to GitHub Secrets**:
   ```bash
   gh secret set UMAMI_WEBSITE_ID --body "your-website-uuid-here"
   ```
7. **Trigger a new release** to rebuild the frontend with analytics enabled

## Environment Variables

**Production (on EC2):**

```bash
# Set in SSM Parameter Store (read by deploy/start-services.sh in dmfenton/compute)
UMAMI_DB_PASSWORD=<generate with: openssl rand -hex 16>
UMAMI_APP_SECRET=<generate with: openssl rand -hex 32>
```

**GitHub Secrets:**

| Secret             | Description                                        |
| ------------------ | -------------------------------------------------- |
| `UMAMI_WEBSITE_ID` | UUID from Umami dashboard (after creating website) |

## Viewing Analytics

- **Dashboard**: https://monet.dmfenton.net/analytics/
- **Public share**: Create a share URL in Umami for read-only access

## Data Collected

Umami is privacy-focused and GDPR compliant:

- Page views, referrers, browsers, devices, countries
- No cookies, no personal data, no tracking across sites
- All data stays on your server
