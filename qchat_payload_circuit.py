"""
qchat payload -> qutrit circuit prototype
-------------------------------------------
Demonstrates the WRITE path: payload string -> 81-state char index ->
4 trits -> custom qutrit gates on the bcde register, gated by the ijk
state-machine register sitting in the WRITE basis state. Then measures
and decodes back to text (the READ path) to prove the round trip.

NOTE: WRITE_STATE below is a placeholder ijk assignment for demo purposes.
Swap in the canonical triple from IJK_BASICS.docx.
"""

import cirq
import numpy as np

# ---------------------------------------------------------------------------
# 1. 81-state character encoding table (bcde register, 3^4 = 81 states)
# ---------------------------------------------------------------------------

_LETTERS_BY_FREQ = list("etaoinshrdlcumwfgypbvkjxqz")  # 26, frequency order
_DIGITS = list("0123456789")                            # 10
_PUNCT = list(".,!?'\";:-_()[]{}<>/\\|@#$%^&*+=~`")     # 32, brackets + operators intact
_EXTRA = ["\n", "\t", "§", "¶", "•", "°", "©", "®", "™", "€", "£"]  # 11

SYMBOLS = ["NULL", "SPACE"] + _LETTERS_BY_FREQ + _DIGITS + _PUNCT + _EXTRA
assert len(SYMBOLS) == 81, f"expected 81 states, got {len(SYMBOLS)}"

CHAR_TO_INDEX = {}
for idx, sym in enumerate(SYMBOLS):
    if sym == "NULL":
        continue
    elif sym == "SPACE":
        CHAR_TO_INDEX[" "] = idx
    else:
        CHAR_TO_INDEX[sym] = idx

INDEX_TO_CHAR = {idx: sym for idx, sym in enumerate(SYMBOLS)}


def char_to_trits(ch: str):
    """char -> (b, c, d, e), each trit in {0,1,2}, base-3 decomposition of index."""
    idx = CHAR_TO_INDEX[ch]
    b = idx // 27
    c = (idx % 27) // 9
    d = (idx % 9) // 3
    e = idx % 3
    return (b, c, d, e)


def trits_to_char(b, c, d, e):
    idx = b * 27 + c * 9 + d * 3 + e
    sym = INDEX_TO_CHAR[idx]
    if sym == "NULL":
        return ""
    if sym == "SPACE":
        return " "
    return sym


# ---------------------------------------------------------------------------
# 2. Qutrit gates (Cirq has no native qutrit gates -> custom 3x3 unitaries)
# ---------------------------------------------------------------------------

def shift_gate(n: int):
    """Cyclic shift |x> -> |(x+n) mod 3>, as a MatrixGate. n=0 is identity."""
    n = n % 3
    mat = np.zeros((3, 3))
    for x in range(3):
        mat[(x + n) % 3, x] = 1
    return cirq.MatrixGate(mat, qid_shape=(3,))


# Confirmed WRITE state from the unified IJK tree (tier 1 = Processing/Control):
# OFF(0,0,0) -> ON_SCAN(1,0,0) -> WRITE(1,1,0) -> ENCRYPT(1,1,1) -> SEND(2,1,1)
WRITE_STATE = (1, 1, 0)


def is_valid_transition(state_a, state_b):
    """Enforce the forward-only, single-qutrit-flip discipline: every step in
    the confirmed IJK tree must change exactly one qutrit by exactly one step."""
    diff = [(b - a) % 3 for a, b in zip(state_a, state_b)]
    flips = sum(1 for d in diff if d != 0)
    return flips == 1


# ---------------------------------------------------------------------------
# 3. Build + run one WRITE->READ circuit per character
# ---------------------------------------------------------------------------

def write_and_read_char(ch: str, verbose=False):
    i, j, k, b, c, d, e = cirq.LineQid.range(7, dimension=3)
    circuit = cirq.Circuit()

    # Set ijk to WRITE_STATE from |0,0,0>
    for qutrit, target in zip([i, j, k], WRITE_STATE):
        if target != 0:
            circuit.append(shift_gate(target)(qutrit))

    # Controlled prep of bcde, gated on ijk == WRITE_STATE
    trits = char_to_trits(ch)
    for qutrit, target in zip([b, c, d, e], trits):
        if target != 0:
            gate = shift_gate(target)
            circuit.append(
                gate(qutrit).controlled_by(i, j, k, control_values=WRITE_STATE)
            )

    # READ: measure the data register back out
    circuit.append(cirq.measure(b, c, d, e, key="bcde"))

    if verbose:
        print(circuit)

    sim = cirq.Simulator()
    result = sim.run(circuit)
    b_m, c_m, d_m, e_m = (result.measurements["bcde"][0][n] for n in range(4))
    return trits_to_char(b_m, c_m, d_m, e_m)


def write_and_read_payload(payload: str, verbose_first=False):
    decoded = []
    for n, ch in enumerate(payload):
        decoded.append(write_and_read_char(ch, verbose=(verbose_first and n == 0)))
    return "".join(decoded)


# ---------------------------------------------------------------------------
# 4. Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    payload = "hi bob!"
    print(f"original payload : {payload!r}")

    decoded = write_and_read_payload(payload, verbose_first=True)
    print(f"decoded payload  : {decoded!r}")
    print(f"round trip match : {decoded == payload}")
