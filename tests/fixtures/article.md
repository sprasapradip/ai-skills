---
title: Laravel Queue Workers in Production: A Practical Setup
description: Run Laravel queue workers in production with Supervisor, sensible retries and monitoring so jobs never silently stall. Config files included.
keyword: laravel queue workers
secondary: supervisor, failed jobs
slug: laravel-queue-workers-production
---
# Laravel Queue Workers in Production

Laravel queue workers process emails, invoices and webhooks outside the request cycle. When they stop, nothing errors on screen. Orders just pile up. This guide shows the setup we run on a 4 GB VPS that handles about 30,000 jobs a day.

## Why laravel queue workers stall

Most stalls come from three causes. A worker runs out of memory and dies. A deploy changes code while old workers keep the previous version in memory. Or a job hangs on a slow API and blocks everything behind it.

Each cause has a fix, and none of them needs a paid service.

## Running workers under supervisor

Supervisor restarts a worker the moment it exits. Create one program block per queue so a slow queue cannot starve a fast one.

```ini
[program:app-worker]
command=php /var/www/app/artisan queue:work redis --sleep=3 --tries=3 --max-time=3600
numprocs=4
autorestart=true
stopwaitsecs=3600
```

The `--max-time` flag recycles each process every hour. That keeps memory flat without you watching it. See the [official queue documentation](https://laravel.com/docs/queues) for every flag.

## Handling failed jobs

Set `--tries` low and use a backoff on the job class. Three attempts with 10, 60 and 300 second gaps cover most flaky APIs. After that the job lands in the `failed_jobs` table, where you can inspect and retry it.

Read our [Redis tuning notes](/blog/redis-tuning-for-laravel) if retries spike after a traffic jump.

## Deploying without stale code

Run `php artisan queue:restart` at the end of every deploy. Workers finish their current job, exit, and Supervisor starts fresh ones with the new code. Skip this and you will debug bugs you already fixed.

## Monitoring that actually alerts

Laravel Horizon gives you a dashboard for Redis queues. Pair it with a heartbeat: schedule a tiny job every minute and alert when it has not run for five. A dashboard you never open is not monitoring.

## FAQ

### How many queue workers should I run?

Start with one per CPU core and measure. Add workers when the wait time on a queue grows during peak hours.

### Do I need Horizon?

No. Horizon helps with Redis queues, but Supervisor plus a heartbeat job covers the essentials.
