import asyncio

from gql import Client
from gql.transport.aiohttp_websockets import AIOHTTPWebsocketsTransport

from .queries import DOWNLOAD_CHANGES, LIBRARY_UPDATE_CHANGES

RETRY_DELAY = 15


class LiveUpdates:
    def __init__(self, suwayomi):
        self.suwayomi = suwayomi
        self.task = None

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self.run())

    def stop(self):
        if self.task:
            self.task.cancel()
            self.task = None
        self.suwayomi.live = False

    async def run(self):
        while True:
            try:
                await self.listen()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(f"live updates stopped, polling instead: {error}")
            self.suwayomi.live = False
            await asyncio.sleep(RETRY_DELAY)
            try:
                await self.suwayomi.logIn()
            except Exception:
                pass

    async def listen(self):
        transport = AIOHTTPWebsocketsTransport(
            url=self.suwayomi.websocketUrl(),
            headers=self.suwayomi.authHeaders(),
            subprotocols=["graphql-transport-ws"],
        )
        async with Client(transport=transport) as session:
            self.suwayomi.live = True
            await asyncio.gather(
                self.watchDownloads(session),
                self.watchLibraryUpdates(session),
            )

    async def watchDownloads(self, session):
        async for result in session.subscribe(DOWNLOAD_CHANGES):
            self.suwayomi.applyDownloadChanges(result['downloadStatusChanged'])

    async def watchLibraryUpdates(self, session):
        async for result in session.subscribe(LIBRARY_UPDATE_CHANGES):
            self.suwayomi.applyLibraryUpdateChanges(result['libraryUpdateStatusChanged'])
