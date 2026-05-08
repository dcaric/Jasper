import asyncio
import sys
import os
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.append(os.getcwd())

async def test_local_fallback():
    print("--- Testing Local Chat Fallback ---")
    
    # Mocking is_gemini_enabled to return False
    with patch("jasper.chat.is_gemini_enabled", return_value=False):
        # Mocking ollama.generate to simulate Gemma 4B response
        mock_response = {"response": "I am Gemma 3 4B, your local assistant!"}
        with patch("ollama.generate", return_value=mock_response) as mock_ollama:
            from jasper.query_handler import process_query
            
            # Simulate a Request object
            mock_request = MagicMock()
            mock_request.json = MagicMock(side_effect=asyncio.coroutine(lambda: {"query": "who are you"}))
            
            print("Processing query: 'who are you' with Gemini DISABLED...")
            result = await process_query(mock_request)
            
            print(f"Result Type: {result.get('type')}")
            print(f"Result Content: {result.get('content')}")
            print(f"Data Sent to Gemini: {result.get('data_sent_to_gemini')}")
            
            # Verify ollama was called
            if mock_ollama.called:
                print("✅ PASSED: Local Ollama model was called as fallback.")
            else:
                print("❌ FAILED: Local Ollama model was NOT called.")

            if result.get("data_sent_to_gemini") == False:
                 print("✅ PASSED: Data sent flag is False (Privacy preserved).")
            else:
                 print("❌ FAILED: Data sent flag is True.")

if __name__ == "__main__":
    from unittest.mock import AsyncMock
    # Re-mocking with AsyncMock for the coroutine
    async def run_test():
        with patch("jasper.chat.is_gemini_enabled", return_value=False):
            # First call for intent detection (JSON), second call for chat response (Text)
            intent_response = {"response": '{"intent": "chat", "params": {}}'}
            chat_response = {"response": "I am Gemma 3 4B, your local assistant!"}
            
            with patch("ollama.generate", side_effect=[intent_response, chat_response]) as mock_ollama:
                from jasper.query_handler import process_query
                
                mock_request = MagicMock()
                mock_request.json = AsyncMock(return_value={"query": "who are you"})
                
                print("Processing query: 'who are you' with Gemini DISABLED...")
                # Note: process_query might return a dict or a JSONResponse
                result = await process_query(mock_request)
                
                # Extract content depending on result type
                if hasattr(result, "body"):
                    import json
                    body = json.loads(result.body.decode())
                    res_type = body.get("type")
                    res_content = body.get("content")
                    res_sent = body.get("data_sent_to_gemini")
                else:
                    res_type = result.get("type")
                    res_content = result.get("content")
                    res_sent = result.get("data_sent_to_gemini")
                
                print(f"Result Type: {res_type}")
                print(f"Result Content: {res_content}")
                print(f"Data Sent to Gemini: {res_sent}")
                
                if mock_ollama.call_count >= 2:
                    print("✅ PASSED: Both intent detection and chat response were called via local model.")
                else:
                    print(f"❌ FAILED: Ollama call count was {mock_ollama.call_count}, expected 2.")
                    
                if res_sent == False:
                     print("✅ PASSED: Data sent flag is False (Privacy preserved).")

    asyncio.run(run_test())
