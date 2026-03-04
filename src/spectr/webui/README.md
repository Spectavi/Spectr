# Spectr Web UI

This directory contains the React frontend for the Spectr web application.

## Development

To run in development mode (requires creating the build first):

```bash
cd src/spectr/webui
npm start
```

The server will be available at http://localhost:3000 and proxy API requests to http://localhost:8020.

## Build

To create a production build:

```bash
cd src/spectr/webui
npm run build
```

This creates an optimized build in the `build/` directory.

## Running the Web Server

Start the Flask backend server with the web UI enabled:

```bash
spectr --webui
```

The web interface will be available at http://localhost:8020

## Features

- Collapsible ticker sidebar
- TradingView chart for 1-minute interval data
- Real-time price updates
- Support for multiple data providers (Alpaca, Robinhood, FMP)

