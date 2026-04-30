import asyncio
import sys
import os

# Add src/sub-agent to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.dependencies import create_worker_service

async def test():
    print("Testing create_worker_service...")
    worker = await create_worker_service()
    print(f"Worker type: {type(worker)}")
    print(f"Task queue type: {type(worker.task_queue)}")
    
    if hasattr(worker.task_queue, 'dequeue'):
        print("SUCCESS: task_queue has dequeue method")
    else:
        print("FAILURE: task_queue MISSING dequeue method")
        print(f"Available attributes: {dir(worker.task_queue)}")

if __name__ == "__main__":
    asyncio.run(test())
