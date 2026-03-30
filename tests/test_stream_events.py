"""
Tests for live SSE activity stream (push_stream_event + queue).
"""
import asyncio
import pytest


@pytest.mark.asyncio
async def test_push_stream_event_delivers_to_queue():
    import memory.store as store

    await store.init()
    await store.push_stream_event("stream-task-1", "loop_start", {"iteration": 1, "max": 5})
    q = store.get_stream_queue("stream-task-1")
    ev = await asyncio.wait_for(q.get(), timeout=2.0)
    assert ev["event_type"] == "loop_start"
    assert ev["data"]["iteration"] == 1
    assert ev["data"]["max"] == 5
    assert "ts" in ev


@pytest.mark.asyncio
async def test_push_stream_event_invalid_type_raises():
    import memory.store as store

    await store.init()
    with pytest.raises(ValueError, match="Invalid stream event_type"):
        await store.push_stream_event("x", "not_a_real_event", {})


@pytest.mark.asyncio
async def test_agent_start_and_step_done():
    import memory.store as store

    await store.init()
    await store.push_stream_event("t2", "agent_start", {"agent": "reasoning"})
    await store.push_stream_event(
        "t2",
        "step_done",
        {"step_id": 1, "status": "success", "preview": "{}", "error": None},
    )
    q = store.get_stream_queue("t2")
    a = await asyncio.wait_for(q.get(), timeout=2.0)
    b = await asyncio.wait_for(q.get(), timeout=2.0)
    assert a["event_type"] == "agent_start"
    assert b["event_type"] == "step_done"
    assert b["data"]["step_id"] == 1
