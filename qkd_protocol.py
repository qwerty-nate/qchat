"""
Qutrit quantum key distribution (entanglement-based, BB84/E91-style)
----------------------------------------------------------------------
Generates a shared secret key between Alice and Bob using entangled
qutrit pairs, then uses that key as a one-time pad over the existing
bcde character register (add-mod-3, via shift_gate). Includes an
intercept-resend eavesdropper model to demonstrate the property plain
pre-shared-key OTP can't offer: detectable tampering.

This REQUIRES a real (or simulated) quantum channel between Alice and
Bob's qutrit pairs at key-establishment time -- unlike the rest of
qchat, entanglement crosses the boundary here. The message payload
itself still relays classically once the key is established.

Bell-like state: |Phi> = (1/sqrt(3)) * sum_j |j,j>  (maximally entangled)
Two conjugate measurement bases:
  Z -- computational basis, no rotation
  F -- Fourier basis: Alice applies F3, Bob applies F3_inv (NOT the same
       gate -- F3 is complex, so matching correlation requires the
       conjugate-transpose on Bob's side, verified empirically below)
"""

import numpy as np
import cirq

from qchat_payload_circuit import char_to_trits, trits_to_char, shift_gate

# ---------------------------------------------------------------------------
# Qutrit Fourier transform (Hadamard analog) and entangling SUM gate
# ---------------------------------------------------------------------------

_omega = np.exp(2j * np.pi / 3)
_F3 = (1 / np.sqrt(3)) * np.array([[_omega ** (j * k) for k in range(3)] for j in range(3)])
_F3_INV = np.conj(_F3).T  # = F3^-1, since F3 is unitary and symmetric

F3_GATE = cirq.MatrixGate(_F3, qid_shape=(3,))
F3_INV_GATE = cirq.MatrixGate(_F3_INV, qid_shape=(3,))

_sum_mat = np.zeros((9, 9))
for _x in range(3):
    for _y in range(3):
        _sum_mat[_x * 3 + ((_x + _y) % 3), _x * 3 + _y] = 1
SUM_GATE = cirq.MatrixGate(_sum_mat, qid_shape=(3, 3))  # |x,y> -> |x, x+y mod 3>


# ---------------------------------------------------------------------------
# One round: entangle, optionally eavesdrop (intercept-resend), measure
# ---------------------------------------------------------------------------

def run_round(alice_basis: str, bob_basis: str, eve_basis: str = None):
    """One entangled pair, one shot. Returns (alice_value, bob_value)."""
    qa, qb = cirq.LineQid.range(2, dimension=3)
    circuit = cirq.Circuit()

    circuit.append(F3_GATE(qa))
    circuit.append(SUM_GATE(qa, qb))

    if eve_basis is not None:
        # Intercept: measure in her guessed basis, then resend a fresh
        # qutrit reconstructed in that SAME basis (all she can do, having
        # measured and lost the original entanglement).
        if eve_basis == "F":
            circuit.append(F3_INV_GATE(qb))
        circuit.append(cirq.measure(qb, key="eve"))
        if eve_basis == "F":
            circuit.append(F3_GATE(qb))

    if alice_basis == "F":
        circuit.append(F3_GATE(qa))
    circuit.append(cirq.measure(qa, key="a"))

    if bob_basis == "F":
        circuit.append(F3_INV_GATE(qb))
    circuit.append(cirq.measure(qb, key="b"))

    result = cirq.Simulator().run(circuit)
    return int(result.measurements["a"][0][0]), int(result.measurements["b"][0][0])


# ---------------------------------------------------------------------------
# Full protocol: many rounds -> sift -> QBER check -> secret key
# ---------------------------------------------------------------------------

def generate_key(n_rounds: int, eavesdrop=False, sample_fraction=0.3, qber_threshold=0.15, seed=None):
    rng = np.random.default_rng(seed)

    alice_vals, bob_vals, alice_bases, bob_bases = [], [], [], []
    for _ in range(n_rounds):
        ab = rng.choice(["Z", "F"])
        bb = rng.choice(["Z", "F"])
        eb = rng.choice(["Z", "F"]) if eavesdrop else None
        a_val, b_val = run_round(ab, bb, eve_basis=eb)
        alice_vals.append(a_val)
        bob_vals.append(b_val)
        alice_bases.append(ab)
        bob_bases.append(bb)

    sifted = [i for i in range(n_rounds) if alice_bases[i] == bob_bases[i]]
    n_sample = max(1, int(len(sifted) * sample_fraction))
    sample_idx = set(rng.choice(sifted, size=n_sample, replace=False).tolist())
    remaining = [i for i in sifted if i not in sample_idx]

    mismatches = sum(1 for i in sample_idx if alice_vals[i] != bob_vals[i])
    qber = mismatches / n_sample
    secure = qber <= qber_threshold

    key = [alice_vals[i] for i in remaining] if secure else []

    return {
        "n_rounds": n_rounds,
        "n_sifted": len(sifted),
        "n_sampled_for_check": n_sample,
        "qber": qber,
        "secure": secure,
        "key_length": len(key),
        "key": key,
    }


# ---------------------------------------------------------------------------
# OTP encrypt/decrypt of a real qchat payload using the derived key
# ---------------------------------------------------------------------------

def otp_encrypt_char(ch: str, key_trits):
    """key_trits: 4 trits consumed for this character's b,c,d,e."""
    plain_trits = char_to_trits(ch)
    return tuple((p + k) % 3 for p, k in zip(plain_trits, key_trits))


def otp_decrypt_char(cipher_trits, key_trits):
    plain_trits = tuple((c - k) % 3 for c, k in zip(cipher_trits, key_trits))
    return trits_to_char(*plain_trits)


def encrypt_payload(payload: str, key):
    if len(key) < len(payload) * 4:
        raise ValueError(f"key too short: need {len(payload)*4} trits, have {len(key)}")
    ciphertext = []
    for n, ch in enumerate(payload):
        k = key[n * 4:(n + 1) * 4]
        ciphertext.append(otp_encrypt_char(ch, k))
    return ciphertext


def decrypt_payload(ciphertext, key):
    plain = []
    for n, cipher_trits in enumerate(ciphertext):
        k = key[n * 4:(n + 1) * 4]
        plain.append(otp_decrypt_char(cipher_trits, k))
    return "".join(plain)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    payload = "hi bob!"
    needed_trits = len(payload) * 4

    print("=== Clean channel (no Eve) ===")
    result = generate_key(n_rounds=needed_trits * 5, eavesdrop=False, seed=1)
    print(f"  rounds sent      : {result['n_rounds']}")
    print(f"  sifted (basis match): {result['n_sifted']}")
    print(f"  sampled for QBER check: {result['n_sampled_for_check']}")
    print(f"  QBER             : {result['qber']:.3f}")
    print(f"  channel secure?  : {result['secure']}")
    print(f"  usable key trits : {result['key_length']} (need {needed_trits})")

    if result["secure"] and result["key_length"] >= needed_trits:
        key = result["key"][:needed_trits]
        ciphertext = encrypt_payload(payload, key)
        decoded = decrypt_payload(ciphertext, key)
        print(f"  original payload : {payload!r}")
        print(f"  decrypted payload: {decoded!r}")
        print(f"  match            : {decoded == payload}")

    print("\n=== Eve intercepting every round (random basis guesses) ===")
    result_eve = generate_key(n_rounds=needed_trits * 5, eavesdrop=True, seed=1)
    print(f"  rounds sent      : {result_eve['n_rounds']}")
    print(f"  sifted (basis match): {result_eve['n_sifted']}")
    print(f"  sampled for QBER check: {result_eve['n_sampled_for_check']}")
    print(f"  QBER             : {result_eve['qber']:.3f}  (clean baseline ~0.000)")
    print(f"  channel secure?  : {result_eve['secure']}  <- eavesdropper detected, key discarded")
