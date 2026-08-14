"""
qchat full chain: WRITE -> ENCRYPT -> SEND_ATTEMPT -> SEND_HERALD_OK ->
SEND_COMPLETE -> RECEIVE -> AWAITING_ACK_RECV -> RECEIVE_CONFIRMED ->
DECRYPT -> READ -> STORE -> DELETE
--------------------------------------------------------------------------------------------
Two SEPARATE 8-qutrit circuits (Alice, Bob) -- no entanglement crosses
between them YET (see teleportation-relay TODOs inline below). Whichever
party is sending for a given message walks the WRITE branch (ijk: OFF ->
ON_SCAN -> WRITE -> ENCRYPT -> SEND_ATTEMPT -> SEND_HERALD_OK ->
SEND_COMPLETE) and produces a classical envelope (op, member_id,
target_id, payload trits) relayed exactly like the WebSocket JSON
envelope. Whichever party is receiving walks the RECEIVE branch (ijk:
OFF -> ON_SCAN -> RECEIVE -> AWAITING_ACK_RECV -> RECEIVE_CONFIRMED ->
DECRYPT -> READ -> STORE -> DELETE) and re-prepares its own bcde
register from those classical trits.

NOTE: SEND_HERALD_OK/SEND_COMPLETE and AWAITING_ACK_RECV/RECEIVE_CONFIRMED
are currently placeholder ijk hops with no real Bell-swap measurement or
classical correction-bit payload wired in -- see inline TODOs in
write_encrypt_send and receive_decrypt_read_store_delete. DELETE was moved
off (2,1,2) to (1,2,2) to free that vector for SEND_HERALD_FAIL, which will
need more downstream logic (retry loop, failure-path circuit) than DELETE
does -- see SEND_HERALD_FAIL below.

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

# Confirmed IJK tree (forward-only, single-qutrit-flip transitions, CYCLIC
# mod-3 -- a trit at 2 rolling to 0 via QutritCycle counts as a legal +1).
# Root: OFF -> ON_SCAN is the branch point; WRITE-branch is the send path
# (now routed through the teleportation-relay herald/ack sub-states),
# RECEIVE-branch is the receive path (same treatment).
STATES = {
    "OFF": (0, 0, 0),
    "ON_SCAN": (1, 0, 0),
    "WRITE": (1, 1, 0),
    "ENCRYPT": (1, 1, 1),
    "SEND_ATTEMPT": (2, 1, 1),        # was SEND -- photon emitted, BSM in flight
    "SEND_HERALD_OK": (2, 2, 1),      # BSM heralded success (this IS the send-side ack)
    "SEND_COMPLETE": (2, 2, 2),       # correction bits transmitted, send done
    "RECEIVE": (1, 0, 1),
    "AWAITING_ACK_RECV": (2, 0, 1),   # waiting on classical correction bits from server
    "RECEIVE_CONFIRMED": (0, 0, 1),   # correction bits received (cyclic i+1 from above)
    "DECRYPT": (0, 1, 1),             # moved off (1,0,2), now reachable from RECEIVE_CONFIRMED
    "READ": (0, 1, 2),                # moved to stay adjacent to new DECRYPT
    "STORE": (1, 1, 2),               # moved to stay adjacent to new READ
    "DELETE": (1, 2, 2),              # moved off (2,1,2) -- that vector now
                                       # reserved for SEND_HERALD_FAIL, which
                                       # has more downstream dependents (retry
                                       # logic) than DELETE does
}
STATES_REV = {v: k for k, v in STATES.items()}

# Ordered walk for each branch -- every consecutive pair here differs by
# exactly one qutrit, one cyclic (mod-3) step forward (verified against
# is_valid_transition in qchat_payload_circuit.py, which is already cyclic).
WRITE_BRANCH = ["OFF", "ON_SCAN", "WRITE", "ENCRYPT",
                "SEND_ATTEMPT", "SEND_HERALD_OK", "SEND_COMPLETE"]
RECEIVE_BRANCH = ["OFF", "ON_SCAN", "RECEIVE", "AWAITING_ACK_RECV",
                   "RECEIVE_CONFIRMED", "DECRYPT", "READ", "STORE", "DELETE"]

# SEND_ATTEMPT can also herald a failure (photon loss / no-click) rather than
# success -- this branch does not advance to SEND_COMPLETE; the caller retries
# from SEND_ATTEMPT. Not walked automatically by _walk; handled in
# write_encrypt_send below based on the simulated herald outcome.
SEND_HERALD_FAIL = (2, 1, 2)  # DELETE moved off this vector (now at (1,2,2))
                               # to free it for SEND_HERALD_FAIL, which has
                               # more downstream dependents (retry/failure
                               # branch logic) than DELETE does. Still not
                               # wired into write_encrypt_send yet -- retry
                               # loop and failure-path circuit not built.

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

    # SEND_ATTEMPT: photon emitted toward server, re-address a from sender -> target
    _walk(circuit, [i, j, k], ["ENCRYPT", "SEND_ATTEMPT"])
    a_delta = (MEMBERS[target] - MEMBERS[sender]) % 3
    if a_delta:
        circuit.append(shift_gate(a_delta)(a))

    # SEND_HERALD_OK / SEND_COMPLETE: placeholder walk only -- these two hops
    # are where the real Bell-swap measurement + classical correction bits
    # belong once the relay is genuinely quantum. Currently just advances ijk
    # with no herald simulation, no BSM failure branch, and no correction-bit
    # payload. TODO: replace with real BSM outcome + SEND_HERALD_FAIL retry
    # path before this is anything more than a state-table placeholder.
    _walk(circuit, [i, j, k], ["SEND_ATTEMPT", "SEND_HERALD_OK", "SEND_COMPLETE"])

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

    # AWAITING_ACK_RECV / RECEIVE_CONFIRMED: placeholder walk only -- same
    # caveat as SEND_HERALD_OK/SEND_COMPLETE above. This is where the
    # classical correction bits (m1, m2) from the server's Bell-swap
    # measurement should actually be consumed and the teleportation
    # correction (Z^(2m1) -> X^(2m2) -> index-negation N, from
    # qchat_teleport.py) applied to bcde, ahead of the existing OTP
    # DECRYPT step below. Not yet wired in.
    _walk(circuit, [i, j, k], ["RECEIVE", "AWAITING_ACK_RECV", "RECEIVE_CONFIRMED"])

    # DECRYPT: mod-3 subtract key_trits back off bcde, gated on ijk == DECRYPT
    _walk(circuit, [i, j, k], ["RECEIVE_CONFIRMED", "DECRYPT"])
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


def run_chain_traced(payload: str, sender="ALICE", target="BOB"):
    """Same round trip as run_chain, but prints a single collapsed trace line
    per branch instead of per-character detail -- e.g.:

        OFF -> ON_SCAN -> WRITE("hi bob!") -> ENCRYPT -> SEND
        RECEIVE -> DECRYPT -> READ("hi bob!") -> STORE

    NOTE: this trace uses the short op names (WRITE/SEND/RECEIVE/DECRYPT/
    READ/STORE) as the intended-behavior view of the pipeline. The actual
    ijk walk underneath now runs through the full herald/ack chain
    (SEND_ATTEMPT -> SEND_HERALD_OK -> SEND_COMPLETE and
    AWAITING_ACK_RECV -> RECEIVE_CONFIRMED) -- this trace deliberately
    collapses those placeholder sub-states rather than exposing them, since
    they don't carry real herald/correction logic yet. Once the BSM
    simulation is wired in, this trace should either show the sub-states or
    a pass/fail branch, not silently pretend they aren't there.
    """
    decoded, log = run_chain(payload, sender=sender, target=target)

    print(f'OFF -> ON_SCAN -> WRITE("{payload}") -> ENCRYPT -> SEND')
    print(f'RECEIVE -> DECRYPT -> READ("{decoded}") -> STORE')

    if decoded != payload:
        print(f'  !!! mismatch: sent "{payload}" but received "{decoded}"')

    return decoded, log


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
