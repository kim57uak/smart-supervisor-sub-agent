import asyncio
import json
from app.core.config import settings

async def check_response():
    print("Checking supervisor.yml setting for a2ui...")
    print(f"Settings: {settings.supervisor_config.get('a2ui')}")
    enabled = settings.supervisor_config.get("a2ui", {}).get("enabled", False)
    print(f"Computed enabled: {enabled}")

if __name__ == "__main__":
    asyncio.run(check_response())
