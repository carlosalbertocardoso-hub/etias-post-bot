import os

# agent.py builds an anthropic.Anthropic() client and publisher.py reads WP_*
# at import time. Tests only exercise pure functions (no real API/HTTP calls),
# so fill in dummy env vars when secrets aren't present (e.g. running locally
# or in CI without repo secrets) purely to satisfy client construction.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("WP_URL", "https://example.invalid")
os.environ.setdefault("WP_USER", "test-user")
os.environ.setdefault("WP_APP_PASSWORD", "test-password")
