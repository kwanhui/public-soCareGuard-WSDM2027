import os

# Unit tests never call a model provider: the guard's automatic screener and the moderation
# baseline are switched off unless a test passes its own screener.
os.environ["SOCAREGUARD_SCREEN"] = "off"
