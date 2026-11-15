# /// script
# requires-python = ">=3.10"
# dependencies = ["keyring>=25"]
# ///
"""Store an API key in Windows Credential Manager (never in a file, never shown on screen).

Run:  uv run stage0/set_key.py gemini
      uv run stage0/set_key.py groq
      uv run stage0/set_key.py gemini --delete
"""
import getpass
import sys

import keyring

SERVICE = "moyo-ai"
NAMES = {"gemini": "gemini_api_key", "groq": "groq_api_key"}

if len(sys.argv) < 2 or sys.argv[1] not in NAMES:
    sys.exit("Usage: set_key.py gemini|groq [--delete]")
name = NAMES[sys.argv[1]]
if "--delete" in sys.argv:
    keyring.delete_password(SERVICE, name)
    print(f"Deleted {name}.")
    sys.exit()
key = getpass.getpass(f"Paste your {sys.argv[1]} API key (hidden), then press Enter: ").strip()
if len(key) < 20:
    sys.exit("That doesn't look like a full key; nothing saved.")
keyring.set_password(SERVICE, name, key)
print(f"Saved to Windows Credential Manager as '{SERVICE} / {name}' (ends with …{key[-4:]}).")
