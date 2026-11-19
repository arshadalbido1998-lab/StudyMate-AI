"""Cancellation primitives for one in-flight mind map generation."""

import asyncio
import logging
import threading
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


class MindMapGenerationCancelled(Exception):
    """Raised when a client stops one mind map generation request."""


class MindMapGenerationCancellation:
    """Thread-safe cancellation with support for cancelling an async HTTP call."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread_id: int | None = None
        self._active_task: asyncio.Task[Any] | None = None
        self._active_task_done = threading.Event()
        self._active_task_done.set()
        self._children: set["MindMapGenerationCancellation"] = set()
        self._close_lock = threading.Lock()
        self.async_groq_client: Any = None
        self.async_openrouter_client: Any = None
        self.async_cloudflare_client: Any = None
        self.gemini_sdk_client: Any = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise MindMapGenerationCancelled("Mind map generation stopped.")

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            loop = self._loop
            task = self._active_task
            children = tuple(self._children)
        for child in children:
            child.cancel()
        if loop is not None and task is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                # The owning request may have completed and closed its loop.
                pass

    def fork(self) -> "MindMapGenerationCancellation":
        """Create a per-worker cancellation scope linked to this generation."""
        child = MindMapGenerationCancellation()
        with self._lock:
            if self.cancelled:
                child.cancel()
            else:
                self._children.add(child)
        child._parent = self
        return child

    def release(self) -> None:
        parent = getattr(self, "_parent", None)
        if parent is not None:
            with parent._lock:
                parent._children.discard(self)
            self._parent = None

    def wait(self, seconds: float) -> None:
        if self._cancelled.wait(max(0.0, seconds)):
            self.check()

    def run_async(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        if self.cancelled:
            coroutine.close()
            self.check()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            coroutine.close()
            raise RuntimeError(
                "Mind map async resources cannot be driven from a running event loop."
            )
        loop = self._loop
        if loop is None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            self._loop_thread_id = threading.get_ident()
        elif self._loop_thread_id != threading.get_ident():
            coroutine.close()
            raise RuntimeError("Mind map async resources must be used from their owning thread.")

        task = loop.create_task(coroutine)
        with self._lock:
            self._active_task = task
            self._active_task_done.clear()
            if self.cancelled:
                loop.call_soon(task.cancel)
        try:
            result = loop.run_until_complete(task)
        except asyncio.CancelledError as error:
            raise MindMapGenerationCancelled("Mind map generation stopped.") from error
        finally:
            with self._lock:
                if self._active_task is task:
                    self._active_task = None
                    self._active_task_done.set()
        self.check()
        return result

    async def aclose(self) -> None:
        """Close owned async clients once, while running on their event loop."""
        current_task = asyncio.current_task()
        with self._lock:
            active_task = self._active_task
        if (
            active_task is not None
            and active_task is not current_task
            and not active_task.done()
        ):
            active_task.cancel()
            await asyncio.gather(active_task, return_exceptions=True)

        with self._lock:
            clients = []
            for attribute in ("async_groq_client", "async_openrouter_client", "async_cloudflare_client"):
                client = getattr(self, attribute)
                if client is not None:
                    setattr(self, attribute, None)
                    clients.append((attribute, client))
            gemini = self.gemini_sdk_client
            self.gemini_sdk_client = None

        for attribute, client in clients:
            try:
                if attribute == "async_cloudflare_client":
                    await client.aclose()
                else:
                    await client.close()
            except Exception:
                logger.exception("Mind map async client cleanup failed: client=%s.", attribute)
        if gemini is not None:
            try:
                await gemini.aio.aclose()
            except Exception:
                logger.exception("Mind map async client cleanup failed: client=gemini.")
            try:
                gemini.close()
            except Exception:
                logger.exception("Mind map SDK cleanup failed: client=gemini.")

    def close(self) -> None:
        with self._close_lock:
            loop = self._loop
            if loop is None or loop.is_closed():
                return

            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None

            if loop.is_running():
                if current_loop is loop:
                    # Async callers should await aclose() in their owning context.
                    loop.create_task(self.aclose())
                    return
                with self._lock:
                    active_task = self._active_task
                if active_task is not None:
                    try:
                        loop.call_soon_threadsafe(active_task.cancel)
                    except RuntimeError:
                        logger.exception("Mind map async task cancellation failed.")
                    self._active_task_done.wait()
                    if not loop.is_running():
                        if current_loop is not None:
                            cleanup_thread = threading.Thread(
                                target=self._close_stopped_loop,
                                args=(loop,),
                                name="mind-map-async-cleanup",
                            )
                            cleanup_thread.start()
                            cleanup_thread.join()
                        else:
                            self._close_stopped_loop(loop)
                        return
                try:
                    asyncio.run_coroutine_threadsafe(self.aclose(), loop).result()
                except Exception:
                    logger.exception("Mind map async cleanup failed on its running event loop.")
                return

            if current_loop is not None:
                # The client loop is stopped but another loop is active on this
                # thread; drive the client loop from a separate cleanup thread.
                cleanup_thread = threading.Thread(
                    target=self._close_stopped_loop,
                    args=(loop,),
                    name="mind-map-async-cleanup",
                )
                cleanup_thread.start()
                cleanup_thread.join()
                return

            self._close_stopped_loop(loop)

    def _close_stopped_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            loop.run_until_complete(self.aclose())
        except Exception:
            logger.exception("Mind map event-loop cleanup failed.")
        finally:
            try:
                loop.close()
            except Exception:
                logger.exception("Mind map event loop close failed.")
            else:
                with self._lock:
                    if self._loop is loop:
                        self._loop = None
                        self._loop_thread_id = None
