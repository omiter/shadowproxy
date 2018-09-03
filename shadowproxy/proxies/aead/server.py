from ... import gvars
from .parser import AEADProtocol
from ..base.server import ProxyBase
from ..shadowsocks.parser import addr_reader


class AEADProxy(ProxyBase):
    proto = "AEAD"

    def __init__(self, cipher, via=None, plugin=None):
        self.cipher = cipher
        self.via = via
        self.plugin = plugin
        self.aead_parser = AEADProtocol(self.cipher).parser()

    async def _run(self):
        if self.plugin:
            self.plugin.server = self
            self.proto += f"({self.plugin.name})"
            await self.plugin.init_server(self.client)

        addr_parser = addr_reader.parser()
        while True:
            data = await self.recv(gvars.PACKET_SIZE)
            if not data:
                break
            addr_parser.send(data)
            if addr_parser.has_result:
                break

        self.target_addr, _ = addr_parser.get_result()
        via_client = await self.connect_server(self.target_addr)

        async with via_client:
            redundant = addr_parser.readall()
            if redundant:
                await via_client.sendall(redundant)
            await self.relay(via_client)

    async def recv(self, size):
        data = await self.client.recv(size)
        if not data:
            return data
        if hasattr(self.plugin, "decode"):
            data = self.plugin.decode(data)
            if not data:
                return await self.recv(size)
        self.aead_parser.send(data)
        data = self.aead_parser.read()
        if not data:
            data = await self.recv(size)
        return data

    async def sendall(self, data):
        packet = b""
        if not hasattr(self, "encrypt"):
            packet, self.encrypt = self.cipher.make_encrypter()
        length = len(data)
        packet += b"".join(self.encrypt(length.to_bytes(2, "big")))
        packet += b"".join(self.encrypt(data))
        if hasattr(self.plugin, "encode"):
            packet = self.plugin.encode(packet)
        await self.client.sendall(packet)
