"""
QChat - Keyboard Input Layer
Frequency-weighted character to qutrit gate sequence mapping
Nate Warner - 2026

DESIGN PHILOSOPHY:
─────────────────────────────────────────────────────────────────────────────
Classical keyboards map keystrokes to ASCII codes sequentially.
QChat maps keystrokes to GATE SEQUENCES by frequency of use.

The most commonly typed characters require the fewest quantum operations
to encode. This minimizes gate depth, reduces decoherence exposure, and
keeps the most-used paths cheapest computationally — exactly analogous
to how Huffman coding assigns shorter bit strings to frequent symbols,
but here the 'cost' is quantum gate complexity in SU(3) space.

FREQUENCY TIERS:
  Tier 0 — Identity only (0 gates):   space
  Tier 1 — Single gate (1 gate):      e t a o i n
  Tier 2 — Two gates (2 gates):       s h r d l c u m w f
  Tier 3 — Three gates (3 gates):     g y p b v k j x q z
  Tier 4 — Compound + phase (4 gates):punctuation . , ! ? ' -

GATE COST MODEL:
  Each Gell-Mann generator applied as U(π) = e^(iπλ/2) costs 1 gate.
  Phase rotations at angles 2π/3 cost 1 gate.
  Compound operations stack additively.
  The qutrit state produced is the output of the full gate sequence
  applied to the ground state |0⟩.

CIRQ INTEGRATION:
  Each character maps to a list of cirq.Gate objects acting on a
  single qutrit (3-level system via cirq.GeneralizedAmplitudeDampingChannel
  or custom unitary via cirq.MatrixGate).
  The gate sequence is a Cirq Circuit that prepares the encoded state.
─────────────────────────────────────────────────────────────────────────────
"""

import numpy as np
from scipy.linalg import expm
import cirq
from gellmann import (
    lambda_1, lambda_2, lambda_3, lambda_4,
    lambda_5, lambda_6, lambda_7, lambda_8,
    ket_0, normalize
)
from qchat_teleport import teleport, create_message

j = 1j

# ── Gate Primitives ────────────────────────────────────────────────────────────
# Each primitive is a full unitary U(π) = e^(iπλ/2) — a maximal rotation.
# Cost: 1 gate each.
# These are the atomic operations of the QChat keyboard.

# X-type flips (symmetric Gell-Mann generators)
X01 = expm(1j * np.pi * lambda_1 / 2)   # |0> <-> |1>  — cheapest flip, 'e'
X02 = expm(1j * np.pi * lambda_4 / 2)   # |0> <-> |2>  — second flip, 't'
X12 = expm(1j * np.pi * lambda_6 / 2)   # |1> <-> |2>  — third flip

# Phase rotations (antisymmetric Gell-Mann generators) at 2π/3
P01 = expm(1j * (2*np.pi/3) * lambda_2 / 2)   # phase in |0>/|1> subspace
P02 = expm(1j * (2*np.pi/3) * lambda_5 / 2)   # phase in |0>/|2> subspace
P12 = expm(1j * (2*np.pi/3) * lambda_7 / 2)   # phase in |1>/|2> subspace

# Diagonal shifts (λ3 and λ8)
D3  = expm(1j * (np.pi/3) * lambda_3 / 2)     # Z-type diagonal shift
D8  = expm(1j * (np.pi/3) * lambda_8 / 2)     # Hypercharge diagonal shift

def apply_sequence(gates, state=None):
    """
    Apply a sequence of gate matrices to a qutrit state.
    Default start state is |0> (ground state).
    Gates applied left to right: G1 then G2 then G3...
    Returns the resulting normalized qutrit state vector.
    """
    if state is None:
        state = ket_0.copy()
    for gate in gates:
        state = gate @ state
    return normalize(state)

# ── Frequency-Weighted Character Map ──────────────────────────────────────────
# Each entry: character -> (gate_sequence, gate_cost, description)
# Gate sequence is a list of unitary matrices applied to |0>.
# Ordered by English letter frequency (Cornell/Oxford corpus data).

CHAR_MAP = {

    # ── TIER 0: Identity (0 gates) ─────────────────────────────────────────
    # Space is the most frequent character in written English (~13% of chars).
    # Ground state |0> — no operation needed.
    ' ': ([], 0, "|0> ground state — no gate"),

    # ── TIER 1: Single gate (1 gate) ──────────────────────────────────────
    # The 6 most frequent letters in English prose.
    # Each maps to a single primitive gate applied to |0>.
    'e': ([X01],  1, "X01|0> → |1>"),                          # ~13% frequency
    't': ([X02],  1, "X02|0> → |2>"),                          # ~9%
    'a': ([P01],  1, "P01|0> → phase-rotated |0>/|1>"),        # ~8%
    'o': ([P02],  1, "P02|0> → phase-rotated |0>/|2>"),        # ~7.5%
    'i': ([D3],   1, "D3|0>  → diagonal shift state"),         # ~7%
    'n': ([D8],   1, "D8|0>  → hypercharge diagonal state"),   # ~6.7%

    # ── TIER 2: Two gates (2 gates) ───────────────────────────────────────
    # Next 10 most frequent letters.
    # Two sequential primitives applied to |0>.
    's': ([X01, P01], 2, "X01 then P01"),     # ~6.3%
    'h': ([X01, P02], 2, "X01 then P02"),     # ~6.1%
    'r': ([X02, P01], 2, "X02 then P01"),     # ~6.0%
    'd': ([X02, P02], 2, "X02 then P02"),     # ~4.3%
    'l': ([X01, X12], 2, "X01 then X12"),     # ~4.0%
    'c': ([X02, X12], 2, "X02 then X12"),     # ~2.8%
    'u': ([P01, P02], 2, "P01 then P02"),     # ~2.8%
    'm': ([X01, D3],  2, "X01 then D3"),      # ~2.4%
    'w': ([X02, D3],  2, "X02 then D3"),      # ~2.4%
    'f': ([X01, D8],  2, "X01 then D8"),      # ~2.2%

    # ── TIER 3: Three gates (3 gates) ─────────────────────────────────────
    # Less frequent letters — compound operations.
    'g': ([X02, D8,  P01], 3, "X02, D8, P01"),    # ~2.0%
    'y': ([P01, X12, D3],  3, "P01, X12, D3"),    # ~2.0%
    'p': ([P02, X01, D8],  3, "P02, X01, D8"),    # ~1.9%
    'b': ([D3,  X01, P02], 3, "D3,  X01, P02"),   # ~1.5%
    'v': ([D8,  X02, P01], 3, "D8,  X02, P01"),   # ~0.98%
    'k': ([X12, P01, D3],  3, "X12, P01, D3"),    # ~0.77%
    'j': ([X12, P02, D8],  3, "X12, P02, D8"),    # ~0.15%
    'x': ([P12, X01, D3],  3, "P12, X01, D3"),    # ~0.15%
    'q': ([P12, X02, D8],  3, "P12, X02, D8"),    # ~0.10%
    'z': ([P12, D3,  D8],  3, "P12, D3,  D8"),    # ~0.07%

    # ── TIER 4: Compound + phase (4 gates) ────────────────────────────────
    # Punctuation and special characters.
    # Highest gate cost — least frequent, most complex states.
    '.': ([X01, P01, X12, D3],  4, "X01, P01, X12, D3"),
    ',': ([X01, P02, X12, D8],  4, "X01, P02, X12, D8"),
    '!': ([X02, P01, X12, D3],  4, "X02, P01, X12, D3"),
    '?': ([X02, P02, X12, D8],  4, "X02, P02, X12, D8"),
    "'": ([P01, P02, D3,  D8],  4, "P01, P02, D3,  D8"),
    '-': ([P12, X01, P01, D8],  4, "P12, X01, P01, D8"),

    # ── NUMERALS (Tier 3-4) ───────────────────────────────────────────────
    '0': ([D3,  D8],           2, "D3, D8"),
    '1': ([X01, D3,  D8],      3, "X01, D3, D8"),
    '2': ([X02, D3,  D8],      3, "X02, D3, D8"),
    '3': ([P01, D3,  D8],      3, "P01, D3, D8"),
    '4': ([P02, D3,  D8],      3, "P02, D3, D8"),
    '5': ([X12, D3,  D8],      3, "X12, D3, D8"),
    '6': ([P12, D3,  D8],      3, "P12, D3, D8"),
    '7': ([X01, X12, D3, D8],  4, "X01, X12, D3, D8"),
    '8': ([X02, X12, D3, D8],  4, "X02, X12, D3, D8"),
    '9': ([P01, X12, D3, D8],  4, "P01, X12, D3, D8"),
}

# ── Cirq Integration ───────────────────────────────────────────────────────────
# Build a Cirq circuit that prepares the encoded qutrit state for a character.
# Uses cirq.MatrixGate to wrap each Gell-Mann unitary.
# The circuit acts on a single qutrit modeled as a 3-level qudit.

def char_to_cirq_circuit(char):
    """
    Convert a character to a Cirq circuit that prepares its qutrit state.

    LOGIC:
      1. Look up the gate sequence for the character
      2. Wrap each unitary matrix as a cirq.MatrixGate
      3. Build a Circuit acting on a single qutrit (dimension=3 qudit)
      4. Return the circuit — executable on Cirq simulators

    Args:
        char: single character (lowercase)
    Returns:
        circuit: cirq.Circuit preparing the encoded state
        cost: gate depth (number of operations)
    """
    char = char.lower()
    if char not in CHAR_MAP:
        raise ValueError(f"Character '{char}' not in QChat keyboard map")

    gates, cost, desc = CHAR_MAP[char]

    # Define a 3-level qudit (qutrit) in Cirq
    qutrit = cirq.LineQid(0, dimension=3)

    # Wrap each unitary as a MatrixGate
    moment_list = []
    for gate_matrix in gates:
        cirq_gate = cirq.MatrixGate(gate_matrix)
        moment_list.append(cirq_gate(qutrit))

    circuit = cirq.Circuit(moment_list)
    return circuit, cost

def char_to_state(char):
    """
    Convert a character directly to its qutrit state vector.
    Applies the gate sequence to |0> and returns the resulting state.

    Args:
        char: single character
    Returns:
        state: normalized 3-vector (qutrit state)
        cost: gate depth
    """
    char = char.lower()
    if char not in CHAR_MAP:
        raise ValueError(f"Character '{char}' not in QChat keyboard map")

    gates, cost, desc = CHAR_MAP[char]
    state = apply_sequence(gates)
    return state, cost

# ── String Encoder ─────────────────────────────────────────────────────────────

def encode_string(text):
    """
    Encode a full string as a sequence of qutrit states.
    Each character becomes a normalized 3-vector ready for teleportation.

    LOGIC:
      Text flows character by character through the keyboard map.
      Each character produces one qutrit state.
      The sequence of states is the quantum message payload.
      Total gate cost reported = sum of all character gate depths.

    Args:
        text: string to encode
    Returns:
        states: list of (char, state_vector, gate_cost) tuples
        total_cost: total gate operations across all characters
    """
    results = []
teleport_ready = []
    total_cost = 0

    for char in text.lower():
        if char in CHAR_MAP:
            state, cost = char_to_state(char)
            results.append((char, state, cost))
            teleport_ready.append(state)
            total_cost += cost
        else:
            # Unknown character — use ground state with flag
            results.append((char, ket_0.copy(), 0))
            teleport_ready.append(ket_0.copy())

    return results, teleport_ready, total_cost

# ── Full Pipeline: Type → Encode → Teleport ───────────────────────────────────

def qchat_send(text, verbose=True):
    """
    Full QChat send pipeline.
    Text → character states → teleport each qutrit → receive on Grid B.

    LOGIC:
      1. Encode text to qutrit state sequence via keyboard map
      2. For each qutrit state, run the teleportation protocol
      3. Collect recovered states on Grid B
      4. Report fidelity per character and total gate cost

    Args:
        text: message string to send
        verbose: print full protocol trace
    Returns:
        recovered_states: list of recovered qutrit states on Grid B
        fidelities: per-character fidelity scores
        total_cost: total gate depth across message
    """
    print(f"\n{'═'*60}")
    print(f"  QChat SEND: \"{text}\"")
    print(f"{'═'*60}")

    encoded, states, total_cost = encode_string(text)

    print(f"\n  Encoding report ({len(text)} characters, {total_cost} total gates):")
    print(f"  {'Char':<8} {'Gate Cost':<12} {'State |ψ>'}")
    print(f"  {'-'*55}")
    for char, state, cost in encoded:
        display = ' ' if char == ' ' else char
        print(f"  '{display}'  {'  '*cost}{'▪'*cost:<10} {np.round(state, 3)}")

    print(f"\n  Teleporting {len(states)} qutrit states...\n")

    recovered_states = []
    fidelities = []

    for i, (char, state, cost) in enumerate(encoded):
        display = ' ' if char == ' ' else char
        if verbose:
            print(f"  [{i+1}/{len(encoded)}] '{display}' (cost={cost})")
        recovered, fidelity = teleport(state, verbose=verbose)
        recovered_states.append(recovered)
        fidelities.append(fidelity)

    mean_fidelity = np.mean(fidelities)
    print(f"\n{'═'*60}")
    print(f"  Transmission complete.")
    print(f"  Characters sent:  {len(text)}")
    print(f"  Total gate cost:  {total_cost}")
    print(f"  Mean fidelity:    {mean_fidelity:.6f}")
    print(f"  {'✓ All states recovered' if mean_fidelity > 0.999 else '✗ Check protocol'}")
    print(f"{'═'*60}\n")

    return recovered_states, fidelities, total_cost

# ── Keyboard Map Inspector ─────────────────────────────────────────────────────

def print_keyboard_map():
    """Print the full QChat keyboard layout sorted by gate cost."""
    print("\nQChat Keyboard Map — Frequency Weighted Gate Assignment")
    print(f"{'Char':<8} {'Tier':<8} {'Gates':<10} {'Description'}")
    print("─" * 60)
    for tier in range(5):
        for char, (gates, cost, desc) in CHAR_MAP.items():
            if cost == tier:
                display = 'SPC' if char == ' ' else f"'{char}'"
                print(f"{display:<8} {tier:<8} {'▪'*cost:<10} {desc}")

def print_cirq_circuit(char):
    """Print the Cirq circuit for a given character."""
    circuit, cost = char_to_cirq_circuit(char)
    display = 'space' if char == ' ' else f"'{char}'"
    print(f"\nCirq circuit for {display} (gate cost = {cost}):")
    print(circuit)

# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("QChat — Keyboard Input Layer")
    print("Frequency-weighted qutrit encoding | Nate Warner 2026")

    # Show keyboard map
    print_keyboard_map()

    # Show Cirq circuits for a few characters
    print("\n── Sample Cirq Circuits ──────────────────────────────────────")
    for char in ['e', 't', 's', 'z']:
        print_cirq_circuit(char)

    # Encode and inspect a word
    print("\n── Encoding 'et' (two most frequent letters) ─────────────────")
    results, states, cost = encode_string("et")
    for char, state, c in results:
        print(f"  '{char}' → {np.round(state, 4)} (cost={c})")

    # Full send pipeline
    qchat_send("hi nate", verbose=False)

    # Gate cost comparison
    print("── Gate Cost Analysis ────────────────────────────────────────")
    test_words = ["the", "quantum", "zephyr"]
    for word in test_words:
        _, _, cost = encode_string(word)
        print(f"  '{word}' → {cost} total gates ({cost/len(word):.1f} avg per char)")
