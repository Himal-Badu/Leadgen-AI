# LocalPulse AI — Landing Page

A cinematic editorial landing page + Stripe checkout flow for LocalPulse AI.

## Design System
- **Background:** Matte charcoal `#181818`
- **Text:** Warm beige `#EBDCC4`
- **Accent:** Coral-rust `#DC9F85`
- **Muted:** Warm gray `#A8A29E`
- **Borders:** 1px solid `rgba(235, 220, 196, 0.15)`
- **Corners:** 4px radius
- **Texture:** 3% opacity fractal noise overlay
- **Typography:** Inter (Google Fonts fallback for Clash Grotesk / General Sans)

## Files
| File | Description |
|------|-------------|
| `index.html` | Main landing page (Hero, Hook, How It Works, Social Proof, Form, Pricing, Footer) |
| `checkout-starter.html` | Starter tier ($29/mo) checkout page |
| `checkout-pro.html` | Pro tier ($79/mo) checkout page |
| `checkout-autopilot.html` | Autopilot tier ($199/mo) checkout page |
| `styles.css` | Shared editorial design system |
| `app.js` | Form submission handler (real API + mock fallback) |

## Deploy

### Option 1: Static Host (Vercel / Netlify)
```bash
cd landing-page
# Deploy with Vercel CLI
vercel --prod

# Or Netlify CLI
netlify deploy --prod --dir=.
```

### Option 2: Serve Locally
```bash
# Python
python -m http.server 8080

# Node
npx serve .
```

Then open `http://localhost:8080`

## Stripe Integration
The checkout pages now call the backend API (`/api/checkout/create`) to generate real Stripe Checkout sessions dynamically. No manual Payment Link configuration needed.

### Environment Variables (for the backend)
```bash
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
export STRIPE_PRICE_STARTER=price_...   # optional — falls back to inline price
export STRIPE_PRICE_PRO=price_...
export STRIPE_PRICE_AUTOPILOT=price_...
```

### Webhook Endpoint
Configure your Stripe webhook to point to:
```
POST /api/webhooks/stripe
```

Subscribe to these events:
- `checkout.session.completed`
- `invoice.paid`
- `customer.subscription.deleted`

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/checkout/create` | POST | Create a Stripe Checkout session |
| `/api/webhooks/stripe` | POST | Receive Stripe webhook events |
| `/api/customers/change-tier` | POST | Upgrade/downgrade subscription |
| `/api/customers/claim-guarantee` | POST | Claim 30-day money-back guarantee |
| `/api/customers/me` | GET | Get customer by email |
| `/api/customers` | GET | List all customers |

## API Integration
The form POSTs to `/api/request-report` by default. If no backend is available, it gracefully falls back to a mock success message. Connect the Flask backend (`web/app.py`) for full functionality.
