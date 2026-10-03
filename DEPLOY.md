# Deploying tts-service to the Hetzner box

Follows the same pattern as FAIS and Quiz Master: the app and its Docker files live in this repo, the nginx vhost is copied into `hetzner-infra`.

Domain: `tts.alphatronex.com` · internal port: `8300` · container: `tts-service`

## 0. Check headroom first

The service holds both models in memory, roughly 1–1.5 GB, and is capped at 2 GB in `docker-compose.prod.yml`.

```bash
ssh hetzner
free -h
docker stats --no-stream
df -h
```

You want at least 2 GB of available memory and 5 GB of free disk (the image is about 1.5 GB, the models about 1 GB). If it is tighter than that, stop and resize the box first.

Also check `hetzner-infra/hetzner.md` that port 8300 is free. If not, change it in `docker-compose.prod.yml` and `deploy/tts.alphatronex.com.conf`.

## 1. DNS

Add an A record `tts` → `5.161.104.5`, then confirm:

```bash
dig +short tts.alphatronex.com
```

## 2. Code onto the server

```bash
sudo mkdir -p /opt/tts-service && sudo chown $USER:$USER /opt/tts-service
git clone https://github.com/alpha-tronex/tts-service.git /opt/tts-service/tts-service
cd /opt/tts-service/tts-service
```

## 3. Secret

```bash
cp .env.production.example .env.production
openssl rand -base64 48        # paste the output as TTS_SHARED_SECRET
nano .env.production
chmod 600 .env.production
```

Keep that value: it also goes into Vercel in step 7.

## 4. Build and start

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker logs -f tts-service      # wait for {"event": "ready", "languages": ["bm", "wo"]}
```

The first start downloads the models (about 1 GB) into the `tts-models` volume and can take a few minutes. Later starts take seconds.

## 5. Try it on the server

```bash
KEY=$(grep TTS_SHARED_SECRET .env.production | cut -d= -f2-)
curl -s http://127.0.0.1:8300/health
curl -s -X POST http://127.0.0.1:8300/speak -H "Content-Type: application/json" -H "X-TTS-Key: $KEY" \
  -d '{"lang":"wo","text":"Na nga def? Maa ngi fi rekk."}' -o wolof.mp3
curl -s -X POST http://127.0.0.1:8300/speak -H "Content-Type: application/json" -H "X-TTS-Key: $KEY" \
  -d '{"lang":"bm","text":"I ni ce. I ka kɛnɛ wa?"}' -o bambara.mp3
ls -l wolof.mp3 bambara.mp3
```

Copy the two files to your Mac and listen (`scp hetzner:/opt/tts-service/tts-service/*.mp3 .`). This is the Week 9 demo, and the first real proof the models load and speak.

## 6. nginx and TLS

```bash
sudo cp deploy/tts.alphatronex.com.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/tts.alphatronex.com.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d tts.alphatronex.com
curl -s https://tts.alphatronex.com/health
```

Copy the vhost Certbot rewrote back into `hetzner-infra/nginx/` so the repo matches the server.

## 7. Tell the translator API about it

In Vercel → the `api` project → Settings → Environment Variables (Production):

| Name | Value |
|---|---|
| `TTS_SERVICE_URL` | `https://tts.alphatronex.com` |
| `TTS_SERVICE_KEY` | the `TTS_SHARED_SECRET` from step 3 |

Then re-run the API's deploy workflow (or push a commit) so the new variables take effect.

## 8. After go-live

- Add an Uptime Kuma HTTP check for `https://tts.alphatronex.com/health`.
- Add the service row (port 8300, container, cert expiry) to `hetzner-infra/hetzner.md`.
- Check `docker stats --no-stream` once more under use.

## Updating later

```bash
cd /opt/tts-service/tts-service && git pull
docker compose -f docker-compose.prod.yml build && docker compose -f docker-compose.prod.yml up -d
```
