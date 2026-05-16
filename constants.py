# Meshtastic's hard limit is 228 UTF-8 bytes; we target this safe margin for all messages.
MAX_BYTES = 200

# When building paginated messages, reserve space for the worst-case [NN/NN] prefix.
PACK_BYTES = MAX_BYTES - 10

USER_AGENT = "MeshtasticBot/1.0 github.com/chhenni/MeshtasticBot"
