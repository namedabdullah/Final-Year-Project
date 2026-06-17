# SAMpai AWS Demo Deploy

Temporary, on-demand AWS deployment kit for the SAMpai final-year-project demo.
Everything in this kit lives under `sampai/deploy/`; no committed deploy artifact
is required in the repository root.

## What This Uses

- One EC2 instance running Docker Compose.
- `data` services: Postgres, Neo4j, Qdrant, Redis.
- `app` services: LightRAG/SAMpai API and the nginx-served SPA.
- Optional `parsing` service: Docling only.
- MinerU is disabled for AWS because the base compose points at a local
  `mineru-cpu:latest` image and it is the heaviest demo dependency.

Only the web edge is published. API, Postgres, Neo4j, Qdrant, Redis, and Docling
remain on the Docker network.

## Files

- `.env.aws.example`: placeholder runtime environment, no secrets.
- `docker-compose.aws.yml`: AWS override for the existing compose stack.
- `docker-compose.cloudflare-tunnel.yml`: optional HTTPS tunnel override that
  removes the public web port and runs `cloudflared`.
- `scripts/init-env.sh`: creates `sampai/deploy/.env.aws` with generated local
  secrets and leaves external secrets as placeholders.
- `scripts/setup-ec2.sh`: installs Docker Compose dependencies on Amazon Linux
  2023 or Ubuntu 22.04 and initializes `.env.aws`.
- `scripts/democtl.sh`: compose wrapper for setup, start, stop, health, logs,
  and volume teardown.

## Required Inputs Before Any AWS Spend

Do not launch anything billable until these are confirmed:

1. AWS account/profile and region.
   Recommended region for Malaysia: `ap-southeast-1` Singapore, or
   `ap-southeast-5` Malaysia if enabled.
2. Whether live document uploads are needed during the defense.
   If not, use `t3.large` and pre-ingest content. If yes, use `t3.xlarge` and
   run Docling during the demo.
3. LLM provider, API key, LLM model, embedding model, and embedding dimension.
4. Cloudflare R2 endpoint, bucket, access key id, and secret access key.
5. Public access choice:
   - HTTP: open `SAMPAI_WEB_PORT` only, typically `8080`.
   - HTTPS: use a Cloudflare Tunnel token in `CLOUDFLARED_TOKEN`.
6. Your current public IP/CIDR for SSH access.

## Cost Plan To Confirm

Use credits only. These are rough ap-southeast-1 Linux on-demand planning
numbers and must be checked in the AWS pricing page or calculator immediately
before launch:

- Pre-ingested demo: `t3.large`, 2 vCPU, 8 GB RAM, 50 GB gp3 EBS.
  Estimated credit burn: about USD 0.12 per demo hour.
- Live upload demo: `t3.xlarge`, 4 vCPU, 16 GB RAM, 50 GB gp3 EBS.
  Estimated credit burn: about USD 0.23 per demo hour.
- Setup/testing can use Spot to reduce credit burn. Use On-Demand for the live
  defense window to avoid interruption.

Exact teardown command for the EC2 instance:

```bash
aws ec2 terminate-instances \
  --profile <aws-profile> \
  --region <region> \
  --instance-ids <instance-id>
```

Also delete AMIs/snapshots when the project is finished:

```bash
aws ec2 deregister-image --profile <aws-profile> --region <region> --image-id <ami-id>
aws ec2 delete-snapshot --profile <aws-profile> --region <region> --snapshot-id <snapshot-id>
```

## Instance Shape

Recommended:

- AMI: Amazon Linux 2023 x86_64 or Ubuntu 22.04 LTS x86_64.
- Instance:
  - `t3.large` for pre-ingested demo content.
  - `t3.xlarge` for live document ingestion during the demo.
- Disk: 50 GB gp3, delete on termination.
- Security group:
  - SSH `22/tcp` from your IP only.
  - HTTP `8080/tcp` from demo audience IPs if not using a tunnel.
  - No inbound web port if using a Cloudflare Tunnel.
  - No public DB/API/parser ports.

Create an AWS Budget and alert before launch. Set a low threshold for actual
spend, for example USD 1, and watch the Credits page during testing.

## On-Instance Setup

After launching and SSH-ing into the instance:

```bash
if command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y git
else
  sudo apt-get update
  sudo apt-get install -y git
fi
git clone --branch codex/aws-demo-deploy <repo-url> ~/Final-Year-Project
cd ~/Final-Year-Project/sampai/deploy
bash scripts/setup-ec2.sh
```

Edit the generated env:

```bash
nano .env.aws
```

Fill every `REPLACE_*` value for LLM, embedding, and R2. Then run:

```bash
bash scripts/democtl.sh setup
bash scripts/democtl.sh start
bash scripts/democtl.sh health
```

For live uploads through Docling:

```bash
# In .env.aws, use the no-image Docling route shown in the comments unless
# VLM_PROCESS_ENABLE and the vlm role are configured.
bash scripts/democtl.sh start-live
```

For Cloudflare Tunnel HTTPS, create a tunnel in Cloudflare Zero Trust with a
public hostname pointing to `http://web:80`, paste its Docker token into
`CLOUDFLARED_TOKEN`, and run:

```bash
bash scripts/democtl.sh start-live-tunnel
```

## Daily Demo Flow

Start:

```bash
cd ~/Final-Year-Project/sampai/deploy
bash scripts/democtl.sh start
```

Live-upload start:

```bash
bash scripts/democtl.sh start-live
```

Live-upload HTTPS start:

```bash
bash scripts/democtl.sh start-live-tunnel
```

Stop between same-day sessions:

```bash
bash scripts/democtl.sh stop
aws ec2 stop-instances --profile <aws-profile> --region <region> --instance-ids <instance-id>
```

Terminate after the defense:

```bash
aws ec2 terminate-instances --profile <aws-profile> --region <region> --instance-ids <instance-id>
```

Destroy local Docker data before making a clean AMI or after test runs:

```bash
SAMPAI_CONFIRM_DESTROY=YES bash scripts/democtl.sh destroy-volumes
```

## AMI Relaunch

After the first successful setup, ingestion, and verification:

```bash
aws ec2 create-image \
  --profile <aws-profile> \
  --region <region> \
  --instance-id <instance-id> \
  --name sampai-demo-$(date +%Y%m%d-%H%M) \
  --no-reboot
```

Each demo day:

1. Launch a new instance from that AMI.
2. Start SAMpai with `bash scripts/democtl.sh start`.
3. Demo.
4. Terminate the instance.

## Verification Checklist

Before declaring the demo ready:

1. `bash scripts/democtl.sh ps` shows all required containers healthy or running.
2. `bash scripts/democtl.sh health` returns success through the nginx edge.
3. The public URL loads the SPA and login works.
4. R2 upload/download works.
5. A document is pre-ingested or live-ingested and entities/graph data populate.
6. Quiz generation succeeds end to end.
7. WebSocket behavior works over the public URL. If using Cloudflare Tunnel,
   confirm the browser connects via `wss://`.

## Known Trade-Offs

- MinerU is disabled. Use Docling or native parsing for the demo.
- With `t3.large`, prefer pre-ingestion. Live parsing can be slow and may starve
  Neo4j/Qdrant/API memory.
- No Elastic IP is required. Prefer the auto-assigned public IP or Cloudflare
  Tunnel. If an Elastic IP is used, release it immediately after teardown.
