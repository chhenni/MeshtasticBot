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
                "user": {"longName": "Dummy Node", "shortName": "DUM"},
                "snr": 8.5,
                "position": {"latitude": DUMMY_LAT, "longitude": DUMMY_LON},
            },
            "!aabbccdd": {
                "user": {"longName": "Test Node Alpha", "shortName": "TNA"},
                "snr": 5.25,
            },
            "!11223344": {
                "user": {"longName": "Test Node Beta", "shortName": "TNB"},
                "snr": -2.0,
            },
        }

    def sendText(self, text: str, channelIndex: int = 0, destinationId: str | None = None) -> None:
        if destinationId:
            print(f"\n[BOT → DM {destinationId}]\n{text}\n")
        else:
            print(f"\n[BOT → ch{channelIndex}]\n{text}\n")

    def close(self) -> None:
        pass


def run_dummy_loop(handler, channel: int, log_channel: int | None = None) -> None:
    """
    Interactive REPL that simulates incoming Meshtastic messages.

    Each line of input is wrapped into a fake packet and passed directly
    to the receive handler. Prefixes:
      dm:<text>    — simulate a direct message
      ch<N>:<text> — simulate a broadcast on channel N (e.g. ch1:hello)
      <text>       — broadcast on the bot's default channel
    """
    print("=" * 55)
    print(" Meshtastic Bot — DUMMY MODE")
    print(f" Fake node: {DUMMY_NODE_ID}  ({DUMMY_LAT}N, {DUMMY_LON}E)")
    print(f" Bot channel: {channel}", end="")
    if log_channel is not None:
        print(f"   Log channel: {log_channel}", end="")
    print()
    print(" Prefixes: 'dm:' for DM, 'ch<N>:' for a specific channel")
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
            elif raw.lower().startswith("ch") and ":" in raw:
                # ch<N>:<message>
                prefix, _, text = raw.partition(":")
                try:
                    pkt_channel = int(prefix[2:])
                except ValueError:
                    print(f"[invalid channel prefix: {prefix}]")
                    continue
                packet = {
                    "decoded": {"text": text.strip()},
                    "fromId": DUMMY_NODE_ID,
                    "toId": "^all",
                    "channel": pkt_channel,
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
