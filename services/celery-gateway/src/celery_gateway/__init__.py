import os

# Overridden at build time via the CELERYHUB_VERSION env baked into the image.
VERSION: str = os.environ.get("CELERYHUB_VERSION", "0.6.0")
