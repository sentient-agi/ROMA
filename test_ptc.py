import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            'http://localhost:8001/generate',
            json={
                'task_description': 'Build a simple email validator',
                'requirements': ['Use regex', 'Return JSON'],
                'language': 'python'
            }
        )
        print(f'Status: {response.status_code}')
        if response.status_code == 200:
            result = response.json()
            print(f'Provider: {result.get("provider")}')
            print(f'Tokens: {result.get("tokens_used")}')
            print(f'Cost: ${result.get("cost_usd")}')
            print(f'Code length: {len(result.get("code", ""))} chars')
            print('\\nFirst 200 chars of code:')
            print(result.get("code", "")[:200])
        else:
            print(f'Error: {response.text}')

asyncio.run(test())
