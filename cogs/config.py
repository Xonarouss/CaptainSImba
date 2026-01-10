import os
import yaml

CONFIG_PATH = os.getenv("BRAND_CONFIG", "config.yaml")

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

async def setup(bot):
    bot.xcfg = load_config()
