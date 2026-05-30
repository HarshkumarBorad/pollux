# Aurora — Frequently Asked Questions

## General

**Q: What is Aurora?**
A managed compute and storage platform for ML and data engineering workloads. On-demand GPU and CPU compute, an S3-compatible object store, CLI/SDK/Desktop clients.

**Q: Which regions are available?**
Frankfurt (`eu-central-1`), Amsterdam (`eu-west-1`), Northern Virginia (`us-east-1`). New regions added based on customer demand.

**Q: How is pricing calculated?**
Compute is billed per second at the instance's hourly rate. Storage at the end of each month based on total GB-hours stored. Egress included up to 10× your stored volume per month.

## Compute

**Q: What instance types are available?**
CPU-only (c-series), GPU with NVIDIA A100 (`gpu-a100`) and H100 (`gpu-h100`), memory-optimized (m-series). See pricing page for current list.

**Q: How long can a job run?**
No hard limit. Customers have run training jobs for over a month. For very long jobs we recommend checkpointing.

**Q: What happens if my job runs out of memory?**
Killed and marked `oom_killed`. Logs preserved up to the kill point. Resubmit with a larger instance type.

## Storage

**Q: Is my data encrypted at rest?**
Yes, AES-256 by default. Customer-managed encryption keys (KMS) on the Enterprise tier.

**Q: Can I use S3-compatible tools?**
Yes. Point any S3 client at `https://s3.aurora.example` with your Aurora credentials. S3 API up to the 2024 version.

## Connectivity & troubleshooting

**Q: How do I troubleshoot connection errors?**
Check firewall and ensure HTTPS to `api.aurora.example:443` is allowed. Corporate proxies need configuration in **Settings → Network**. Check `status.aurora.example` for incidents.

## Support

**Q: How do I contact support?**
Free tier — community forum at `forum.aurora.example`. Pro tier — `support@aurora.example`, 24h response. Enterprise tier — dedicated Slack channel + 1h SLA.

**Q: Where can I see service status?**
Live status page at `status.aurora.example`.
