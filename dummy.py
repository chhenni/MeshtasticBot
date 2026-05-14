"""
Dummy interface for testing the bot without a physical Meshtastic device.

Activate with:  python main.py --dummy
"""

from uuid import uuid4


# Fake GPS position used for all GPS-dependent commands (Oslo city centre)
DUMMY_NODE_ID = "!dummy"
DUMMY_LAT = 59.9139
DUMMY_LON = 10.7522


class DummyInterface:
    """
    Drop-in replacement for a Meshtastic interface.
    Outgoing messages are printed to stdout; incoming messages are fed via
    run_dummy_loop() rather than pubsub.
    """

    @property
    def nodes(self) -> dict:
        return {
            DUMMY_NODE_ID: {
                "position": {
                    "latitude": DUMMY_LAT,
                    "longitude": DUMMY_LON,
                }
            }
        }

    def sendText(self, text: str, channelIndex: int = 0, destinationId: str | None = None) -> None:
        if destinationId:
            print(f"\n[BOT → DM {destinationId}]\n{text}\n")
        else:
            print(f"\n[BOT → ch{channelIndex}]\n{text}\n")

    def close(self) -> None:
        pass


def run_dummy_loop(handler, channel: int) -> None:
    """
    Interactive REPL that simulates incoming Meshtastic messages.

    Each line of input is wrapped into a fake packet and passed directly
    to the receive handler. Prefix a message with 'dm:' to simulate a
    direct message (e.g.  dm:/weather).
    """
    print("=" * 55)
    print(" Meshtastic Bot — DUMMY MODE")
    print(f" Fake node: {DUMMY_NODE_ID}  ({DUMMY_LAT}N, {DUMMY_LON}E)")
    print(f" Listening on channel {channel}")
    print(" Prefix with 'dm:' to simulate a direct message")
    print(" Ctrl+C or Ctrl+D to exit")
    print("=" * 55)

    try:
        while True:
            try:
                raw = input("> ").strip()
            except EOFError:
                break

            if not raw:
                continue

            if raw.lower().startswith("dm:"):
                text = raw[3:].strip()
                packet = {
                    "decoded": {"text": text},
                    "fromId": DUMMY_NODE_ID,
                    "toId": DUMMY_NODE_ID,
                    "channel": 0,
                    "id": str(uuid4()),
                }
            else:
                packet = {
                    "decoded": {"text": raw},
                    "fromId": DUMMY_NODE_ID,
                    "toId": "^all",
                    "channel": channel,
                    "id": str(uuid4()),
                }

            handler(packet)

    except KeyboardInterrupt:
        pass

    print("\nDummy mode exiting.")
