# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (PyPI) | ✅ |
| older releases | ❌ — please upgrade |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it **responsibly** — do **not** open a public GitHub issue.

### How to Report

1. **Email** [luongnv89@gmail.com](mailto:luongnv89@gmail.com) with the subject line `[SECURITY] music-cli — <brief description>`
2. Include as much detail as possible (see below)
3. You will receive an acknowledgment within **48 hours**

### What to Include

- Type of vulnerability (e.g., command injection, path traversal)
- Full paths of affected source files
- Location of the affected source code (tag / branch / commit or URL)
- Step-by-step instructions to reproduce
- Proof-of-concept or exploit code if possible
- Estimated impact

### What to Expect

- Acknowledgment within 48 hours
- Regular progress updates
- Credit in the security advisory (if you wish)
- Notification when the fix is released

## Security Best Practices for Contributors

- Never commit secrets, API keys, or credentials
- Use environment variables for sensitive configuration
- Avoid `shell=True` in subprocess calls unless strictly necessary
- Follow OWASP secure coding guidelines
- Report any security concerns immediately via the process above
