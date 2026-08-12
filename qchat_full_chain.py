"""
qchat full chain: WRITE -> ENCRYPT -> SEND -> RECEIVE -> DECRYPT -> READ -> STORE -> DELETE
--------------------------------------------------------------------------------------------
Two SEPARATE 8-qutrit circuits (Alice, Bob) -- no entanglement crosses
between them. Whichever party is sending for a given message walks the
WRITE branch (ijk: OFF -> ON_SCAN -> WRITE -> ENCRYPT -> SEND) and
produces a classical envelope (op, member_id, target_id, payload trits)
relayed exactly like the WebSocket JSON envelope. Whichever party is
receiving walks the RECEIVE branch (ijk: OFF -> ON_SCAN -> RECEIVE ->
DECRYPT -> READ -> STORE -> DELETE) and re-prepares its own bcde
register from those classical trits.

Both parties use the SAME two functions below -- the branch taken is a
per-message role, not a fixed per-party identity. Either Alice or Bob
can write/encrypt/send, and either can receive/decrypt/read/store/delete.

Register layout per circuit: i, j, k, a, b, c, d, e  (8 qutrits)
  ijk  -- state machine tier/op register (confirmed IJK tree, single-flip
          transitions only -- see STATES / branches below)
  a    -- single qutrit for member identity: SERVER=0, ALICE=1, BOB=2
          (caps this scheme at exactly 3 addressable identities --
          fine for the closed 3-cage test, but a 4th party needs a
          wider register)
  bcde -- 81-state character register (same as before)
"""

import cirq

from qchat_payload_circuit import char_to_trits, trits_to_char, shift_gate

# Confirmed IJK tree (forward-only, single-qutrit-flip transitions).
# Root: OFF -> ON_SCAN is the branch point; WRITE-branch is the send
# path, RECEIVE-branch is the receive path.
STATES = {
    "OFF": (0, 0, 0),
    "ON_SCAN": (1, 0, 0),
    "WRITE": (1, 1, 0),
    "ENCRYPT": (1, 1, 1),
    "SEND": (2, 1, 1),
    "RECEIVE": (1, 0, 1),
    "DECRYPT": (1, 0, 2),
    "READ": (1, 1, 2),
    "STORE": (2, 1, 2),
    "DELETE": (2, 2, 2),
}
STATES_REV = {v: k for k, v in STATES.items()}

# Ordered walk for each branch -- every consecutive pair here differs by
# exactly one qutrit, one step forward (verified against is_valid_transition
# in qchat_payload_circuit.py).
WRITE_BRANCH = ["OFF", "ON_SCAN", "WRITE", "ENCRYPT", "SEND"]
RECEIVE_BRANCH = ["OFF", "ON_SCAN", "RECEIVE", "DECRYPT", "READ", "STORE", "DELETE"]

MEMBERS = {"SERVER": 0, "ALICE": 1, "BOB": 2}
MEMBERS_REV = {v: k for k, v in MEMBERS.items()}


def _walk(circuit, qutrits, branch):
    """Step ijk through a branch one state at a time, one qutrit-flip per step."""
    for from_name, to_name in zip(branch, branch[1:]):
        from_state, to_state = STATES[from_name], STATES[to_name]
        for qutrit, s1, s2 in zip(qutrits, from_state, to_state):
            delta = (s2 - s1) % 3
            if delta:
                circuit.append(shift_gate(delta)(qutrit))


def write_encrypt_send(ch: str, sender: str, target: str, key_trits=(0, 0, 0, 0), verbose=False):
    """Either party can call this when they are the one sending a character.

    key_trits: per-character OTP keystream trits from the negotiated QKD
    session key (qkd_protocol.py). Defaults to (0,0,0,0) -- identity/no-op --
    when no session key is wired in yet.
    """
    if sender not in MEMBERS or target not in MEMBERS:
        raise ValueError(f"unregistered member: sender={sender!r} target={target!r}")

    i, j, k, a, b, c, d, e = cirq.LineQid.range(8, dimension=3)
    circuit = cirq.Circuit()

    _walk(circuit, [i, j, k], ["OFF", "ON_SCAN"])
    if MEMBERS[sender]:
        circuit.append(shift_gate(MEMBERS[sender])(a))

    # WRITE: prep bcde with the plaintext char, gated on ijk == WRITE
    _walk(circuit, [i, j, k], ["ON_SCAN", "WRITE"])
    trits = char_to_trits(ch)
    for qutrit, tgt in zip([b, c, d, e], trits):
        if tgt:
            circuit.append(shift_gate(tgt)(qutrit).controlled_by(i, j, k, control_values=STATES["WRITE"]))

    # ENCRYPT: mod-3 OTP add of key_trits onto bcde, gated on ijk == ENCRYPT
    _walk(circuit, [i, j, k], ["WRITE", "ENCRYPT"])
    for qutrit, kt in zip([b, c, d, e], key_trits):
        if kt:
            circuit.append(shift_gate(kt)(qutrit).controlled_by(i, j, k, control_values=STATES["ENCRYPT"]))

    # SEND: re-address a from sender -> target
    _walk(circuit, [i, j, k], ["ENCRYPT", "SEND"])
    a_delta = (MEMBERS[target] - MEMBERS[sender]) % 3
    if a_delta:
        circuit.append(shift_gate(a_delta)(a))

    circuit.append(cirq.measure(i, j, k, key="ijk"))
    circuit.append(cirq.measure(a, key="a"))
    circuit.append(cirq.measure(b, c, d, e, key="bcde"))

    if verbose:
        print(circuit)

    result = cirq.Simulator().run(circuit)
    ijk_m = tuple(int(x) for x in result.measurements["ijk"][0])
    a_m = int(result.measurements["a"][0][0])
    bcde_m = tuple(int(x) for x in result.measurements["bcde"][0])

    return {
        "op": STATES_REV[ijk_m],
        "member_id": sender,
        "target_id": MEMBERS_REV[a_m],
        "payload_char": ch,
        "payload_trits": bcde_m,  # ciphertext trits -- what actually crosses the wire
    }


def receive_decrypt_read_store_delete(envelope, seq, key_trits=(0, 0, 0, 0), self_id="BOB", verbose=False):
    """Either party can call this when they are the one receiving a character.

    key_trits must be the same keystream used at write_encrypt_send time
    (mod-3 OTP is its own inverse under addition, so DECRYPT reuses key_trits
    directly rather than negating it).
    """
    if envelope["member_id"] not in MEMBERS or envelope["target_id"] != self_id:
        raise ValueError(f"rejected: unregistered or misaddressed envelope {envelope}")

    i, j, k, a, b, c, d, e = cirq.LineQid.range(8, dimension=3)
    circuit = cirq.Circuit()

    _walk(circuit, [i, j, k], ["OFF", "ON_SCAN"])
    sender_id = MEMBERS[envelope["member_id"]]
    if sender_id:
        circuit.append(shift_gate(sender_id)(a))

    # RECEIVE: prep bcde with the ciphertext trits, gated on ijk == RECEIVE
    _walk(circuit, [i, j, k], ["ON_SCAN", "RECEIVE"])
    for qutrit, tgt in zip([b, c, d, e], envelope["payload_trits"]):
        if tgt:
            circuit.append(shift_gate(tgt)(qutrit).controlled_by(i, j, k, control_values=STATES["RECEIVE"]))

    # DECRYPT: mod-3 subtract key_trits back off bcde, gated on ijk == DECRYPT
    _walk(circuit, [i, j, k], ["RECEIVE", "DECRYPT"])
    for qutrit, kt in zip([b, c, d, e], key_trits):
        if kt:
            circuit.append(shift_gate(-kt % 3)(qutrit).controlled_by(i, j, k, control_values=STATES["DECRYPT"]))

    # READ: measure bcde (now plaintext)
    _walk(circuit, [i, j, k], ["DECRYPT", "READ"])
    circuit.append(cirq.measure(b, c, d, e, key="bcde"))

    # STORE: log checkpoint, measure ijk for the log entry
    _walk(circuit, [i, j, k], ["READ", "STORE"])
    circuit.append(cirq.measure(i, j, k, key="ijk_store"))

    if verbose:
        print(circuit)

    result = cirq.Simulator().run(circuit)
    bcde_m = tuple(int(x) for x in result.measurements["bcde"][0])
    ijk_store = tuple(int(x) for x in result.measurements["ijk_store"][0])
    decoded_char = trits_to_char(*bcde_m)

    # DELETE: classically-controlled correction back to NULL (0,0,0,0) on
    # bcde -- a unitary alone can't reset an unknown/measured state to |0>,
    # so this re-preps the register into the observed classical value (same
    # pattern RECEIVE uses to re-prep from a classical envelope) and then
    # applies the inverse shift for that specific observed value.
    delete_circuit = cirq.Circuit()
    for qutrit, observed in zip([b, c, d, e], bcde_m):
        if observed:
            delete_circuit.append(shift_gate(observed)(qutrit))
            delete_circuit.append(shift_gate(-observed % 3)(qutrit))
    delete_circuit.append(cirq.measure(b, c, d, e, key="bcde_deleted"))
    delete_result = cirq.Simulator().run(delete_circuit)
    bcde_deleted = tuple(int(x) for x in delete_result.measurements["bcde_deleted"][0])
    assert bcde_deleted == (0, 0, 0, 0), "DELETE failed to erase bcde to NULL"

    log_entry = {
        "seq": seq,
        "op": "DELETE",
        "checkpoint_op": STATES_REV[ijk_store],
        "from": envelope["member_id"],
        "to": self_id,
        "char": decoded_char,
    }
    return decoded_char, log_entry


def run_chain(payload: str, sender="ALICE", target="BOB", verbose_first=False):
    """Symmetric round trip: pass sender="BOB", target="ALICE" to run it the
    other direction -- both parties can walk either branch."""
    decoded_chars = []
    log = []
    for n, ch in enumerate(payload):
        envelope = write_encrypt_send(ch, sender, target, verbose=(verbose_first and n == 0))
        decoded_char, log_entry = receive_decrypt_read_store_delete(
            envelope, seq=n + 1, self_id=target, verbose=(verbose_first and n == 0)
        )
        decoded_chars.append(decoded_char)
        log.append(log_entry)
    return "".join(decoded_chars), log


if __name__ == "__main__":
    payload = "hi bob!"
    print(f"original payload : {payload!r}\n")
    decoded, log = run_chain(payload, sender="ALICE", target="BOB", verbose_first=True)
    print("\nclassical log (DELETE entries on Bob's side):")
    for entry in log:
        print(f"  {entry}")
    print(f"\ndecoded payload  : {decoded!r}")
    print(f"round trip match : {decoded == payload}")

    print("\n--- reverse direction: Bob writes, Alice receives ---")
    reply = "hey alice"
    print(f"original payload : {reply!r}\n")
    decoded2, log2 = run_chain(reply, sender="BOB", target="ALICE", verbose_first=False)
    print(f"decoded payload  : {decoded2!r}")
    print(f"round trip match : {decoded2 == reply}")
