
import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

# Mock problematic imports before they are loaded
sys.modules['unidecode'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.genai'] = MagicMock()
sys.modules['google.genai.types'] = MagicMock()

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock connectors to avoid heavy initialization
with patch('jasper.app.connectors', {}), \
     patch('jasper.app.GmailConnector', MagicMock()), \
     patch('jasper.app.OutlookConnector', MagicMock()), \
     patch('jasper.app.FileConnector', MagicMock()), \
     patch('jasper.app.SemanticConnector', MagicMock()), \
     patch('jasper.app.get_setting', return_value='GMAIL'), \
     patch('jasper.app.log_event', MagicMock()):
    
    from jasper import app

    async def test_coding_mode():
        print("Testing 'coding on'...")
        class MockRequest:
            async def json(self):
                return {"query": "coding on"}

        resp = await app.process_query(MockRequest())
        print(f"Response (coding on): {resp}")
        assert resp.get("coding_mode") == True
        assert "ON" in resp.get("content")

        print("\nTesting script generation...")
        # Mock handle_coding_task to avoid real LLM call
        async def mock_handle(input):
            return {"type": "chat", "content": "Script saved to JaspersScripts/hello.py", "coding_mode": True}
        
        with patch('jasper.app.handle_coding_task', side_effect=mock_handle):
            class MockRequestScript:
                async def json(self):
                    return {"query": "create a hello world script"}
            
            resp_script = await app.process_query(MockRequestScript())
            print(f"Response (script gen): {resp_script}")
            assert resp_script.get("coding_mode") == True
            assert "JaspersScripts" in resp_script.get("content")

        print("\nTesting 'coding off'...")
        class MockRequestOff:
            async def json(self):
                return {"query": "coding off"}

        resp_off = await app.process_query(MockRequestOff())
        print(f"Response (coding off): {resp_off}")
        assert resp_off.get("coding_mode") == False
        assert "OFF" in resp_off.get("content")

        print("\nAll backend logic checks passed!")

    if __name__ == "__main__":
        asyncio.run(test_coding_mode())
