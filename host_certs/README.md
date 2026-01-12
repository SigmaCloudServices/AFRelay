# `host_certs/` Folder

This folder is intended to store cryptographic files used as Docker volumes, such as:

- Private keys (`.key`)
- Certificates (`.pem`, `.crt`, `.pfx`)
- Certificate Signing Requests (`.csr`)

These files are mounted inside the container at `app_certs/`.

**Never upload these files to GitHub.**