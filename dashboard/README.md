# Trading Bot Dashboard

A modern, responsive React dashboard for monitoring and controlling the trading bot.

## Features

- **Real-time Dashboard**: Monitor bot status, positions, trades, and P&L
- **Operator Controls**: Toggle trading modes, pause/resume operations, emergency stop
- **AI Advisor**: View AI-powered market analysis and trading recommendations
- **Opportunities**: Browse and filter potential trading setups
- **Dark Theme**: Professional dark mode optimized for trading
- **Responsive Design**: Works on desktop, tablet, and mobile devices

## Tech Stack

- **React 18** with TypeScript
- **Vite** for fast development and optimized builds
- **Tailwind CSS** for styling
- **shadcn/ui** components
- **React Router** for navigation
- **Recharts** for data visualization
- **Lucide React** for icons

## Development

### Prerequisites

- Node.js 18+ and npm

### Installation

```bash
npm install
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:
```
VITE_API_URL=http://localhost:8000
```

### Development Server

```bash
npm run dev
```

Open http://localhost:5173 in your browser.

### Build for Production

```bash
npm run build
```

The build output will be in the `dist/` directory.

### Preview Production Build

```bash
npm run preview
```

## Docker Deployment

### Build the Docker Image

```bash
docker build -t trading-bot-dashboard .
```

### Run the Container

```bash
docker run -p 80:80 trading-bot-dashboard
```

The dashboard will be available at http://localhost

### Environment Variables in Docker

Pass environment variables at build time:

```bash
docker build --build-arg VITE_API_URL=https://api.example.com -t trading-bot-dashboard .
```

## Project Structure

```
dashboard/
├── src/
│   ├── api/              # API client
│   │   └── client.ts     # API endpoints and types
│   ├── components/       # Reusable components
│   │   ├── ui/           # shadcn/ui components
│   │   ├── StatusCard.tsx
│   │   ├── TradeTable.tsx
│   │   └── PnLChart.tsx
│   ├── pages/            # Page components
│   │   ├── Dashboard.tsx
│   │   ├── Controls.tsx
│   │   ├── AIOverview.tsx
│   │   └── Opportunities.tsx
│   ├── lib/              # Utilities
│   │   └── utils.ts
│   ├── App.tsx           # Main app with routing
│   ├── main.tsx          # Entry point
│   └── index.css         # Global styles
├── public/               # Static assets
├── Dockerfile            # Docker configuration
├── nginx.conf            # Nginx configuration
└── package.json          # Dependencies
```

## API Integration

The dashboard connects to the trading bot's webhook service API. Update `VITE_API_URL` to point to your API endpoint.

### Mock Data

Currently, the dashboard uses mock data for demonstration. To integrate with the real API:

1. Ensure the webhook service is running
2. Update the API URL in `.env`
3. The API client in `src/api/client.ts` will automatically connect

## Safety Features

- **Confirmation Dialogs**: Critical actions (mode toggle, emergency stop) require confirmation
- **Warning Alerts**: Clear warnings for risky operations
- **Mode Indicators**: Always shows current trading mode (dry-run/live)
- **AI Disclaimer**: AI recommendations are clearly marked as advisory only

## Customization

### Theming

Modify colors in `src/index.css` under the `:root` CSS variables.

### Components

All UI components are in `src/components/ui/` and can be customized as needed.

## License

This dashboard is part of the trading bot project.
