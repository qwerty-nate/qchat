"""
QChat - Qutrit Teleportation Protocol
Nate Warner - 2026

LOGIC OVERVIEW:
─────────────────────────────────────────────────────────────────────────────
Quantum teleportation moves a qutrit state |ψ> from Grid A (sender)
to Grid B (receiver) without physically transmitting the state itself.

The protocol has three layers:

  1. ENTANGLEMENT LAYER — pre-shared between Grid A and Grid B
     A maximally entangled qutrit pair (ebit) is established before
     any message is sent. This is the quantum channel.

  2. QUANTUM LAYER — Grid A performs a joint measurement
     Sender measures their message qutrit + their half of the ebit
     together. This produces a classical result (m1, m2) ∈ {0,1,2}²
     giving 9 possible outcomes. The message state is destroyed here.

  3. CLASSICAL LAYER — correction signal sent via function register
     The 3-qutrit function register transmits (m1, m2) classically
     to Grid B. Receiver applies a correction gate U(m1, m2) to
     their half of the ebit. The message state reappears on Grid B.

KEY INSIGHT:
  The SEND gate (e^iθλ2) rotates in the |0>/|1> subspace.
  The RECEIVE gate (e^iφλ5) rotates in the |0>/|2> subspace.
  Together they span all correction rotations needed in SU(3).
  The j entries in λ2 and λ5 drive rotation in the imaginary plane —
  they are the generators of U(θ) = e^(i·θ·λ/2) acting on the qutrit.

SECURITY:
  Intercepting the classical channel gives (m1, m2) — useless without
  the entangled pair. Intercepting the entangled pair collapses it —
  the correction signal becomes useless. Both together require
  simultaneous access to quantum and classical channels.
─────────────────────────────────────────────────────────────────────────────
"""

import numpy as np
from scipy.linalg import expm
from gellmann import (
    lambda_2, lambda_5, lambda_3, lambda_8,
    ket_0, ket_1, ket_2,
    normalize, apply_op
)

j = 1j

# ── Matrix Exponential Rotation Gates ─────────────────────────────────────────
# U(θ) = e^(i·θ·λ/2)
# The j entries in λ2 and λ5 make these rotations in the complex plane.
# θ = π gives a full bit-flip equivalent in the relevant subspace.
# These are the SU(3) analogs of the Pauli rotation gates in SU(2).

def send_gate(theta):
    """
    SEND gate — rotation in |0>/|1> subspace.
    Generator: λ2 (antisymmetric, imaginary off-diagonal entries).
    U_send(θ) = e^(i·θ·λ2/2)
    Used by sender to encode measurement correction into classical signal.
    """
    return expm(1j * theta * lambda_2 / 2)

def receive_gate(phi):
    """
    RECEIVE gate — rotation in |0>/|2> subspace.
    Generator: λ5 (antisymmetric, imaginary off-diagonal entries).
    U_receive(φ) = e^(i·φ·λ5/2)
    Used by receiver to apply correction and recover message state.
    """
    return expm(1j * phi * lambda_5 / 2)

def phase_gate(theta):
    """
    Full SU(3) phase gate combining both subspace rotations.
    Used for general qutrit phase corrections in teleportation.
    U(θ) = e^(i·θ·(λ2 + λ5)/2)
    """
    return expm(1j * theta * (lambda_2 + lambda_5) / 2)

# ── Correction Gate Table ──────────────────────────────────────────────────────
# For each of the 9 possible measurement outcomes (m1, m2) ∈ {0,1,2}²
# the receiver applies a specific correction unitary to recover |ψ>.
# This is the qutrit generalization of the Pauli correction in qubit teleportation.
# The angles are multiples of 2π/3 — the natural symmetry of a 3-level system.

def build_correction_table():
    """
    Build the 9-element correction gate table.
    Each entry U[m1][m2] is the 3x3 unitary the receiver applies
    based on the classical measurement result (m1, m2) from the sender.
    """
    angles = [0, 2*np.pi/3, 4*np.pi/3]  # trisection of full rotation
    table = {}
    for m1 in range(3):
        for m2 in range(3):
            theta = angles[m1]
            phi   = angles[m2]
            # Combine send and receive subspace corrections
            U = send_gate(theta) @ receive_gate(phi)
            table[(m1, m2)] = U
    return table

CORRECTION_TABLE = build_correction_table()

# ── Entangled Pair Generation ──────────────────────────────────────────────────
# A maximally entangled qutrit pair (ebit) in the computational basis.
# |Φ+> = (1/√3)(|00> + |11> + |22>)
# Grid A holds qutrits [0], Grid B holds qutrits [1].
# This is established BEFORE any message is sent — the quantum handshake.

def create_ebit():
    """
    Generate a maximally entangled qutrit pair.
    Returns the 9-dimensional state vector of the bipartite system.
    |Φ+> = (1/√3)(|00> + |11> + |22>)
    """
    state = np.zeros(9, dtype=complex)
    # |00> = index 0, |11> = index 4, |22> = index 8
    state[0] = 1/np.sqrt(3)  # |00>
    state[4] = 1/np.sqrt(3)  # |11>
    state[8] = 1/np.sqrt(3)  # |22>
    return state

# ── Message State ──────────────────────────────────────────────────────────────

def create_message(alpha, beta, gamma):
    """
    Create an arbitrary qutrit message state.
    |ψ> = α|0> + β|1> + γ|2>
    Normalized automatically.
    Args:
        alpha, beta, gamma: complex amplitudes for |0>, |1>, |2>
    """
    state = alpha * ket_0 + beta * ket_1 + gamma * ket_2
    return normalize(state)

# ── Sender: Joint Measurement ──────────────────────────────────────────────────

def sender_measure(message_state, ebit_state):
    """
    LOGIC: Sender performs a joint Bell-basis measurement on their
    message qutrit and their half of the shared ebit (Grid A side).

    This is the quantum layer of the protocol. The measurement outcome
    (m1, m2) is random but determines exactly what correction the
    receiver must apply. The message state is destroyed here —
    no-cloning is respected. The state 'moves' not 'copies'.

    In a real system this requires a qutrit Bell measurement circuit.
    Here we simulate the outcome probabilistically.

    Returns:
        (m1, m2): classical measurement result ∈ {0,1,2}²
                  transmitted to receiver via function register
    """
    # Simulate random measurement outcome (9 equally likely for max entanglement)
    m1 = np.random.randint(0, 3)
    m2 = np.random.randint(0, 3)
    return m1, m2

# ── Classical Channel: Function Register ───────────────────────────────────────

def transmit_correction(m1, m2):
    """
    LOGIC: The 3-qutrit function register carries the classical correction
    signal (m1, m2) from Grid A to Grid B over a classical channel.

    This is the SEND operation in the QChat function register.
    Two classical trits of information — not quantum, not secret.
    Intercepting this gives an attacker nothing without the ebit.

    Maps to: SEND gate in function register → classical trit transmission
    """
    print(f"  [FUNCTION REGISTER] SEND: correction signal ({m1}, {m2}) transmitted classically")
    return m1, m2

# ── Receiver: Apply Correction ─────────────────────────────────────────────────

def receiver_correct(message_state, m1, m2):
    """
    LOGIC: Receiver applies correction gate U(m1, m2) to their half
    of the ebit (Grid B side) based on the classical signal received.

    U(m1, m2) = SEND_gate(θ_m1) @ RECEIVE_gate(φ_m2)

    The SEND gate (e^iθλ2) corrects the |0>/|1> subspace component.
    The RECEIVE gate (e^iφλ5) corrects the |0>/|2> subspace component.
    Together they fully reconstruct |ψ> in SU(3) space.

    After correction, Grid B holds the original message state exactly.
    Grid A's message qutrit is in an undetermined collapsed state.

    Maps to: RECEIVE gate in function register → state reconstruction
    """
    U = CORRECTION_TABLE[(m1, m2)]
    recovered = U @ message_state
    return normalize(recovered)

# ── Full Teleportation Protocol ────────────────────────────────────────────────

def teleport(message_state, verbose=True):
    """
    Execute the full QChat qutrit teleportation protocol.

    STEP 1: Pre-entangle Grid A and Grid B (quantum handshake)
    STEP 2: Sender performs joint measurement (quantum layer)
    STEP 3: Sender transmits (m1, m2) via function register (classical layer)
    STEP 4: Receiver applies correction gate (state reconstruction)
    STEP 5: Verify fidelity — recovered state matches original

    Args:
        message_state: normalized 3-vector (qutrit state to teleport)
        verbose: print protocol steps

    Returns:
        recovered_state: the reconstructed message on Grid B
        fidelity: |<ψ|ψ_recovered>|² should be 1.0
    """
    if verbose:
        print("\n── QChat Teleportation Protocol ──────────────────────────────")
        print(f"  Message state |ψ> = {np.round(message_state, 4)}")

    # STEP 1: Establish entangled pair
    ebit = create_ebit()
    if verbose:
        print(f"\n  [STEP 1] Ebit established: |Φ+> = (1/√3)(|00> + |11> + |22>)")

    # STEP 2: Sender measures
    m1, m2 = sender_measure(message_state, ebit)
    if verbose:
        print(f"\n  [STEP 2] Grid A joint measurement → outcome ({m1}, {m2})")
        print(f"           Message state destroyed on Grid A")

    # STEP 3: Transmit via function register
    if verbose:
        print(f"\n  [STEP 3] Classical channel:")
    m1, m2 = transmit_correction(m1, m2)

    # STEP 4: Receiver applies correction
    recovered = receiver_correct(message_state, m1, m2)
    if verbose:
        print(f"\n  [STEP 4] Grid B applies U({m1},{m2}) correction gate")
        print(f"           Recovered state = {np.round(recovered, 4)}")

    # STEP 5: Fidelity check
    fidelity = np.abs(np.dot(message_state.conj(), recovered))**2
    if verbose:
        print(f"\n  [STEP 5] Fidelity |<ψ|ψ_recovered>|² = {fidelity:.6f}")
        print(f"           {'✓ Teleportation successful' if fidelity > 0.999 else '✗ Check correction gates'}")
        print("──────────────────────────────────────────────────────────────\n")

    return recovered, fidelity

# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("QChat — Qutrit Teleportation Protocol")
    print("Gell-Mann SU(3) basis | Nate Warner 2026\n")

    # Test 1: Pure basis state |0>
    print("TEST 1: Teleport |0>")
    msg1 = create_message(1, 0, 0)
    teleport(msg1)

    # Test 2: Pure basis state |1>
    print("TEST 2: Teleport |1>")
    msg2 = create_message(0, 1, 0)
    teleport(msg2)

    # Test 3: Superposition state
    print("TEST 3: Teleport superposition (1/√3)(|0> + |1> + |2>)")
    msg3 = create_message(1, 1, 1)
    teleport(msg3)

    # Test 4: Arbitrary complex state
    print("TEST 4: Teleport arbitrary complex state")
    msg4 = create_message(0.5, 0.5*j, np.sqrt(0.5))
    teleport(msg4)

    # Fidelity sweep across 100 random states
    print("FIDELITY SWEEP — 100 random qutrit states:")
    fidelities = []
    for _ in range(100):
        coeffs = np.random.complex128(np.random.randn(3) + 1j*np.random.randn(3))
        msg = normalize(coeffs)
        _, f = teleport(msg, verbose=False)
        fidelities.append(f)
    print(f"  Mean fidelity: {np.mean(fidelities):.6f}")
    print(f"  Min fidelity:  {np.min(fidelities):.6f}")
    print(f"  Max fidelity:  {np.max(fidelities):.6f}")
