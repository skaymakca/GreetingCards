"""macOS Keychain storage for the Anthropic API key."""

import logging

# noinspection PyUnresolvedReferences
from Security import (  # type: ignore[import-untyped]
    SecItemAdd,  # pyright: ignore[reportAttributeAccessIssue]
    SecItemCopyMatching,  # pyright: ignore[reportAttributeAccessIssue]
    SecItemDelete,  # pyright: ignore[reportAttributeAccessIssue]
    SecItemUpdate,  # pyright: ignore[reportAttributeAccessIssue]
    errSecItemNotFound,  # pyright: ignore[reportAttributeAccessIssue]
    errSecSuccess,  # pyright: ignore[reportAttributeAccessIssue]
    kSecAttrAccount,  # pyright: ignore[reportAttributeAccessIssue]
    kSecAttrService,  # pyright: ignore[reportAttributeAccessIssue]
    kSecClass,  # pyright: ignore[reportAttributeAccessIssue]
    kSecClassGenericPassword,  # pyright: ignore[reportAttributeAccessIssue]
    kSecMatchLimit,  # pyright: ignore[reportAttributeAccessIssue]
    kSecMatchLimitOne,  # pyright: ignore[reportAttributeAccessIssue]
    kSecReturnData,  # pyright: ignore[reportAttributeAccessIssue]
    kSecValueData,  # pyright: ignore[reportAttributeAccessIssue]
)

logger = logging.getLogger(__name__)

_SERVICE = "com.kaymakcalan.app.greetingcards"
_ACCOUNT = "anthropic-api-key"


def get_api_key() -> str | None:
    """Read the API key from macOS Keychain. Returns None if not found."""
    query = {
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: _SERVICE,
        kSecAttrAccount: _ACCOUNT,
        kSecReturnData: True,
        kSecMatchLimit: kSecMatchLimitOne,
    }
    status, result = SecItemCopyMatching(query, None)
    if status == errSecSuccess and result:
        return bytes(result).decode("utf-8")
    return None


def save_api_key(key: str) -> None:
    """Write the API key to macOS Keychain (insert or update)."""
    key = key.strip()
    query = {
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: _SERVICE,
        kSecAttrAccount: _ACCOUNT,
    }
    update_attrs = {kSecValueData: key.encode("utf-8")}
    status = SecItemUpdate(query, update_attrs)
    if status == errSecItemNotFound:
        attrs = dict(query)
        attrs[kSecValueData] = key.encode("utf-8")
        status, _ = SecItemAdd(attrs, None)
    if status != errSecSuccess:
        logger.error("Keychain save failed (OSStatus %d)", status)
        raise OSError(f"Failed to save API key to Keychain (OSStatus {status})")


def delete_api_key() -> None:
    """Remove the API key from macOS Keychain."""
    query = {
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: _SERVICE,
        kSecAttrAccount: _ACCOUNT,
    }
    status = SecItemDelete(query)
    if status not in (errSecSuccess, errSecItemNotFound):
        logger.error("Keychain delete failed (OSStatus %d)", status)
