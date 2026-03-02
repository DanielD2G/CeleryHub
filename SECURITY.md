# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in CeleryHub, please report it responsibly.

**Do not open a public issue.** Instead, email the maintainers directly or use [GitHub's private vulnerability reporting](https://github.com/DanielD2G/CeleryHub/security/advisories/new).

We will acknowledge your report within 48 hours and aim to release a fix within 7 days for critical issues.

## Scope

CeleryHub is a monitoring dashboard typically deployed on private or internal networks. The following are in scope:

- Authentication bypass in the `CELERYHUB_AUTH_TOKEN` middleware
- Injection vulnerabilities (SQL, command, XSS)
- Unauthorized access to Celery control operations
- Information disclosure through API endpoints

## Security Considerations

- CeleryHub does **not** include built-in user authentication. Use a reverse proxy (nginx, Traefik, Cloudflare Tunnel) for production deployments.
- Set `CELERYHUB_AUTH_TOKEN` to protect destructive control endpoints (shutdown, purge, revoke).
- Configure `CORS_ORIGINS` to restrict cross-origin access.
- Use `rediss://` broker URLs for Redis TLS connections.
