# Flight Ticket Watcher — Web Dashboard

Next.js 15 dashboard for monitoring flight prices across routes and dates.

## Development

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Production

Docker is the primary deployment method:

```bash
docker build -t flight-ticket-watcher-web .
docker run -p 3000:3000 flight-ticket-watcher-web
```

Alternatively, build and start directly:

```bash
npm run build
npm start
```
