# Security Policy

Lockd is a security hardening tool that runs privileged operations on the
systems it protects. Vulnerability reports are taken seriously and handled
with priority over all other work.

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✓         |
| < 1.0   | ✗         |

Only the latest release receives security fixes. There is no backporting.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Preferred channel: open a **confidential issue** on GitLab:
https://gitlab.com/Ricardo23B/Lockd/-/issues/new — check the
"This issue is confidential" box. Confidential issues are visible only to
the project maintainer.

Please include, where possible:
- Affected version (`lockd --version`) and distribution.
- A description of the issue and its security impact.
- Steps to reproduce, or a proof of concept.
- Whether the issue requires local access, an existing user account, or
  prior privileges.

## What to expect

Lockd is maintained by a single developer. Realistic commitments:

- **Acknowledgement** of your report within **7 days**.
- An initial assessment (accepted / needs info / out of scope) within
  **14 days**.
- Fixes for confirmed vulnerabilities are prioritized over all feature and
  maintenance work, and released as soon as they are ready and tested.
- You will be credited in the changelog and release notes unless you prefer
  otherwise.

Coordinated disclosure: please allow up to **90 days** from acknowledgement
before public disclosure. If a fix ships earlier, disclose freely once the
release is out.

## Scope

**In scope** — anything that breaks Lockd's own security model, e.g.:
- Privilege escalation through Lockd (the Polkit helper, the pkexec
  boundary, module script resolution, path validation).
- Dry-run mode performing real changes.
- The journal, backups or state being forgeable or bypassable by an
  unprivileged user.
- A module damaging system integrity beyond its documented impact
  (e.g. breaking authentication, locking the administrator out).
- Tampering with Lockd's own files in ways that survive its integrity
  assumptions.

**Out of scope:**
- The inherent security trade-offs of a hardening decision that Lockd
  documents (e.g. "disabling USB storage blocks USB storage"). If the
  *documentation* of an impact is wrong or misleading, that IS in scope.
- Vulnerabilities in third-party software that Lockd installs or configures
  (ClamAV, Fail2ban, UFW…) — report those upstream. If Lockd *configures*
  them insecurely, that IS in scope.
- Attacks requiring an already-root attacker.
- Social engineering, physical access.

## Security model (summary)

For reviewers and researchers, the key properties Lockd claims — and which
you are invited to try to break:

1. All privileged operations pass through a single root-owned helper
   (`lockd-helper`) invoked via Polkit; the helper only executes module
   scripts from root-owned, non-user-writable paths declared in
   `modules.yaml`.
2. `--dry-run` never modifies the system.
3. Every privileged operation is recorded in an append-only journal
   (`/var/lib/lockd/journal.jsonl`) with per-operation backup manifests.
4. Reported module state is verified against the real system, not trusted
   from cached files.
5. A hardcoded never-touch list protects authentication and system
   infrastructure (polkit, sudo, dbus, PAM, mount) from Lockd's own
   modules, regardless of configuration.

A violation of any of these properties is a vulnerability. Reports that
demonstrate one are especially welcome.
