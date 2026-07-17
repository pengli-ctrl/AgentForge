# Security Policy

## Supported Versions

AgentForge is an open-source project. Security fixes are applied to the latest
major release only.

| Version | Supported          |
|---------|--------------------|
| 3.x     | :white_check_mark: |
| 2.x     | :x: (EOL)          |
| 1.x     | :x: (EOL)          |

## Reporting a Vulnerability

If you discover a security vulnerability in AgentForge, please report it
responsibly:

1. **Do NOT open a public GitHub issue.**
2. Send an email to **pl2847253@gmail.com** with:
   - A description of the vulnerability
   - Steps to reproduce (proof of concept if possible)
   - Potential impact assessment
   - Suggested fix (if any)
3. You will receive an acknowledgment within **48 hours**.
4. A fix or mitigation will be provided within **7 days** for critical issues,
   or **30 days** for non-critical issues.

## Response Timeline

| Severity | Acknowledgment | Fix Target  |
|----------|---------------|-------------|
| Critical | 48 hours      | 7 days      |
| High     | 48 hours      | 14 days     |
| Medium   | 72 hours      | 30 days     |
| Low      | 72 hours      | Next release |

## Security Best Practices

### API Key Management

- **Never commit API keys** to version control. Use environment variables or
  a secrets manager.
- Rotate API keys periodically (recommended: every 90 days).
- Use different API keys for development and production environments.
- API keys are compared using constant-time comparison to prevent timing attacks.

### Network Isolation

- Deploy AgentForge behind a reverse proxy (Nginx, Traefik) with TLS termination.
- Restrict database (MySQL) and cache (Redis) access to the AgentForge
  application network only — do not expose these ports publicly.
- Use Docker network isolation (as configured in `docker-compose.yml`) to
  separate services.
- Enable firewall rules to limit inbound traffic to the API port (8000) only.

### LLM Gateway Security

- vLLM endpoints should be on a private network, not exposed to the internet.
- Use API key authentication for the vLLM service.
- Set appropriate rate limits to prevent abuse.

### Tool Sandbox

- Code execution tools run in Docker containers with resource limits.
- Do not mount host directories with sensitive data into tool sandboxes.
- Use read-only mounts where possible.

### Data Protection

- Task input data may contain source code — ensure MySQL is encrypted at rest.
- Redis snapshots contain context data — enable Redis AUTH and TLS if
  transmitting over untrusted networks.
- Trace data may contain payload summaries — review what is logged before
  enabling debug-level tracing in production.
