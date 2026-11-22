# TSF Connect Bootstrap — security design

Status: design stage. This repository does not yet contain an executable installer.

## Repository boundaries

- `SCORP365/TSF` is public and contains only the small bootstrap entrypoint, its trust material, and operator documentation.
- `SCORP365/TSF-Connect` remains private and contains the TSF Connect application and server installer.
- The public bootstrap must never contain private application source, credentials, access tokens, or server configuration.

## Intended operator flow

1. The operator downloads and verifies a pinned bootstrap release.
2. The bootstrap checks that it is running on a supported Ubuntu host and explains required privileges.
3. It starts GitHub App Device Flow using the public Client ID. It displays the GitHub verification URL, one-time user code, and a QR code for that URL.
4. The operator approves access in GitHub. The bootstrap polls only at the interval returned by GitHub and handles pending, slow-down, expiry, and denial responses.
5. The bootstrap uses the resulting short-lived GitHub App user token only in HTTPS Authorization headers to retrieve the private repository. It must not place tokens in command arguments, URLs, logs, shell history, or persistent environment files.
6. Before executing any private code, it verifies a signed release manifest against a public verification key pinned in this repository's bootstrap trust root. The manifest identifies the exact private repository commit and hashes of the installer payload.
7. It extracts only validated archive paths into a root-owned staging directory, checks file hashes, and then invokes the unified installer.
8. It removes temporary credentials and downloaded staging data when safe to do so.

## Trust and release rules

- Never download executable code from a moving branch name such as `main` or `latest`.
- A commit SHA or HTTPS transport alone is not a sufficient authenticity guarantee for executable installer code.
- The bootstrap must verify a cryptographic signature over a manifest before running private code.
- The signing private key must not be stored in either repository or on the production VPS. The public verification key may be embedded in the bootstrap.
- A failed, missing, expired, or invalid signature/hash check is a hard stop. There is no insecure override.
- Changes to the bootstrap itself require review and a new pinned release/checksum.

## GitHub App

The intended GitHub App is `TSF Connect Installer` with Device Flow enabled and read-only Contents/Metadata permissions, installed only for the private `TSF-Connect` repository. The public bootstrap repository does not need to be added to that app installation.

The Client ID is public configuration. No Client Secret, personal access token, or interactive `gh auth login` is required for the target VPS.

## Explicit non-goals

- No DNS, firewall, ISPmanager, Nginx, TLS, SSH, mail, or unrelated service changes during bootstrap authentication.
- No production deployment or service installation until the unified installer has passed isolated-VM testing and the operator explicitly approves deployment.
- No token persistence or background refresh for this bootstrap flow unless a separately reviewed update design demonstrates that it is necessary.

## Open implementation gate

Before an executable bootstrap is published, implement and test QR rendering, Device Flow polling, token redaction/cleanup, archive path validation, signature verification, manifest generation, and end-to-end installation in an isolated Ubuntu VM. The signature format and key-generation/rotation procedure must be finalized before the first trusted release.
