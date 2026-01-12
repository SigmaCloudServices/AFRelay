# `app_certs/` Folder

This folder is used internally by the web service to access cryptographic files, such as:

- Private keys (`.key`)
- Certificates (`.pem`, `.crt`, `.pfx`)
- Certificate Signing Requests (`.csr`)

Files placed in the host folder `host_certs/` are mounted here as a Docker volume.  

For security reasons, these files are excluded from the repository using `.gitignore`.

**Never upload these files to GitHub.**