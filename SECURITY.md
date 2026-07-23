# Security policy

Please do not disclose vulnerabilities in a public issue. Contact the repository maintainer privately and include affected versions, reproduction steps, and potential impact.

Before deploying Ticket Kanban:

- Set a long random `SECRET_KEY`.
- Serve the application through HTTPS.
- Keep `.env`, databases, reports, and backups outside version control.
- Restrict Google sign-in to an approved Workspace domain when applicable.
- Keep `GOOGLE_AUTO_PROVISION=False` unless open registration is intentional.
- Review administrator and technician accounts regularly.
