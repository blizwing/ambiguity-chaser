import os

# llm_client builds its client at import time; tests mock every call, so a
# placeholder key is enough. (If a real .env exists, load_dotenv uses it, but
# no test here makes a real API call: every model call is monkeypatched.)
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-real")
