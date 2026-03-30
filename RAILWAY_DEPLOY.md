# Deploy to Railway in 5 Minutes

## Step 1 — Fork the repo

Click **Fork** on GitHub.

## Step 2 — Create Railway account

Go to [railway.app](https://railway.app) → Login with GitHub.

## Step 3 — New Project

Railway → **New Project** → **Deploy from GitHub**  
Select your forked repo.

## Step 4 — Add Environment Variables

In Railway dashboard → **Variables** tab:

| Variable | Example |
|----------|---------|
| `ANTHROPIC_API_KEY` | your Anthropic key |
| `JWT_SECRET` | click **Generate** or use `openssl rand -base64 32` |
| `AUTH_MODE` | `jwt` |
| `ADMIN_EMAIL` | your@email.com |
| `ADMIN_PASSWORD` | strong password |

Copy optional keys from `.railway.env.example` if you use billing.

## Step 5 — Deploy

Click **Deploy** → Wait 3–5 minutes.  
Your URL: `https://yourapp.railway.app`

## Step 6 — Custom Domain (optional)

Railway → **Settings** → **Domains** → Add Custom Domain  
Point your DNS to Railway.

## Pricing

Railway Hobby: about **$5/month**.  
With Anthropic API usage, total cost is often roughly **₹2,500–5,000/month** depending on volume (estimate only).
