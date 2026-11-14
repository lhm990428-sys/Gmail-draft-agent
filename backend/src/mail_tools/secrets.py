"""Use Windows Credential Manager explicitly; never select a plaintext fallback."""
import sys

SERVICE = "hermes-mail/dev/v1"
NAMES = ("openai-api-key", "langsmith-api-key", "gmail-oauth-token", "artifact-encryption-key", "console-session-key", "hermes-command-key")


def vault():
    if sys.platform != "win32":
        raise RuntimeError("This setup profile requires Windows Credential Manager")
    from keyring.backends.Windows import WinVaultKeyring
    return WinVaultKeyring()


def get_secret(name: str) -> str | None:
    if name not in NAMES:
        raise ValueError("Unsupported secret name")
    return vault().get_password(SERVICE, name)


def put_secret(name: str, value: str) -> None:
    if name not in NAMES or not value.strip():
        raise ValueError("Unsupported name or empty secret")
    vault().set_password(SERVICE, name, value.strip())


def delete_secret(name: str) -> None:
    if name not in NAMES:
        raise ValueError("Unsupported secret name")
    vault().delete_password(SERVICE, name)
