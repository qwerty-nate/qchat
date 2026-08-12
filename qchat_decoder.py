"""
QChat - Decoder (Grid B)
Recovers characters from received qutrit states after teleportation
Nate Warner - 2026

LOGIC OVERVIEW:
─────────────────────────────────────────────────────────────────────────────
The decoder is the inverse of the keyboard layer. Grid B receives a sequence
of qutrit states from the teleportation protocol and must identify which
character each state corresponds to.

THE CORE PROBLEM — you cannot directly read a quantum state:
  Measurement collapses a qutrit to one of {|0>, |1>, |2>}.
  A single measurement destroys the superposition information.
  Most QChat states are superpositions — direct measurement loses data.

THE SOLUTION — state discrimination via fidelity matching:
  Pre-compute a reference library of all encoded character states.
  For each received state, compute the fidelity F = |<ref|received>|²
  against every entry in the library.
  The character with highest fidelity F > threshold is the decoded output.
  This is a quantum state discrimination problem — no measurement needed,
  just inner products between complex vectors.

  F = |<ψ_ref | ψ_received>|²
    = 1.0  → perfect match
    = 0.0  → orthogonal states (completely different character)

THRESHOLD:
  F > 0.999 → confirmed match (accounts for floating point precision)
  F > 0.95  → near match (accounts for real hardware noise)
  F < 0.95  → unknown / decoding error

NOISE MODEL:
  Real qutrit hardware introduces decoherence.
  The decoder includes a depolarizing noise model that simulates
  realistic fidelity degradation and tests decoder robustness.
  Noise level σ controls the standard deviation of state perturbation.

INVERSE GATE APPROACH (alternative):
  For each received state, apply the inverse gate sequence (U†...U2†U1†)
  and check if result is close to |0>. This is the 'undo everything'
  approach. Included as a secondary verification method.
─────────────────────────────────────────────────────────────────────────────
"""

import numpy as np
from gellmann import ket_0, normalize
from qchat_keyboard import (
    CHAR_MAP, char_to_state, encode_string,
    apply_sequence, X01, X02, X12, P01, P02, P12, D3, D8
)
from qchat_teleport import teleport

# ── Reference State Library ────────────────────────────────────────────────────
# Pre-compute all encoded character states at initialization.
# This is Grid B's lookup table — built once, used for every decode.
# Each entry: character → reference state vector

def build_reference_library():
    """
    Build the complete reference state library for all QChat characters.

    LOGIC:
      For every character in CHAR_MAP, apply its gate sequence to |0>
      and store the resulting state vector. This is the ground truth
      that received states are matched against during decoding.

      The library is deterministic — same gates always produce same state.
      No quantum randomness here, this is classical pre-computation.

    Returns:
        library: dict { char -> np.array(3,) complex state vector }
    """
    library = {}
    for char, (gates, cost, desc) in CHAR_MAP.items():
        state = apply_sequence(gates)
        library[char] = state
    return library

REFERENCE_LIBRARY = build_reference_library()

# ── Inverse Gate Map ───────────────────────────────────────────────────────────
# Each gate primitive is unitary — its inverse is its conjugate transpose U†.
# Applying the inverse sequence in reverse order undoes the encoding.
# U1 U2 U3 |0> = |ψ>  →  U3† U2† U1† |ψ> = |0>

INVERSE_GATES = {
    'X01': X01.conj().T,   # X01† — self-inverse (X² = I) with phase
    'X02': X02.conj().T,
    'X12': X12.conj().T,
    'P01': P01.conj().T,   # Phase gate inverse = negative rotation
    'P02': P02.conj().T,
    'P12': P12.conj().T,
    'D3':  D3.conj().T,
    'D8':  D8.conj().T,
}

def build_inverse_sequence(char):
    """
    Build the inverse gate sequence for a character.
    Applying this to the encoded state should return |0>.

    LOGIC:
      If encoding is G1 G2 G3 |0> = |ψ>
      Then decoding is G3† G2† G1† |ψ> = |0>
      Reverse the gate list and conjugate transpose each gate.
    """
    gates, cost, desc = CHAR_MAP[char]
    return [g.conj().T for g in reversed(gates)]

# ── Fidelity Discriminator ─────────────────────────────────────────────────────

def fidelity(state_a, state_b):
    """
    Compute quantum state fidelity between two qutrit states.
    F = |<a|b>|² ∈ [0, 1]
    F = 1.0 → identical states
    F = 0.0 → orthogonal states

    This is the core of the decoder — no measurement, just inner product.
    """
    return np.abs(np.dot(state_a.conj(), state_b))**2

def decode_state(received_state, threshold=0.999, noise_tolerant=False):
    """
    Decode a single received qutrit state to its character.

    LOGIC:
      1. Compute fidelity F between received state and every reference state
      2. Find the character with maximum fidelity
      3. If F_max > threshold → return that character
      4. If noise_tolerant=True, lower threshold to 0.95 for noisy hardware
      5. If no match → return '?' (decoding failure)

    Args:
        received_state: normalized 3-vector from Grid B after teleportation
        threshold: minimum fidelity to confirm a match (default 0.999)
        noise_tolerant: if True, use 0.95 threshold for real hardware
    Returns:
        char: decoded character
        best_fidelity: fidelity score of the best match
        match_confirmed: bool — True if above threshold
    """
    if noise_tolerant:
        threshold = 0.95

    best_char = '?'
    best_fidelity = 0.0

    for char, ref_state in REFERENCE_LIBRARY.items():
        f = fidelity(ref_state, received_state)
        if f > best_fidelity:
            best_fidelity = f
            best_char = char

    match_confirmed = best_fidelity > threshold
    return best_char, best_fidelity, match_confirmed

def decode_sequence(received_states, threshold=0.999, noise_tolerant=False, verbose=True):
    """
    Decode a sequence of received qutrit states to a string.

    LOGIC:
      Apply decode_state() to each received state in sequence.
      Concatenate decoded characters to reconstruct the original message.
      Report per-character fidelity and any decoding failures.

    Args:
        received_states: list of normalized 3-vectors from Grid B
        threshold: fidelity threshold for confirmed match
        noise_tolerant: use relaxed threshold for noisy hardware
        verbose: print decoding trace
    Returns:
        decoded_text: reconstructed string
        decode_report: list of (char, fidelity, confirmed) per state
    """
    decoded_chars = []
    decode_report = []

    if verbose:
        print(f"\n── Grid B Decoding ───────────────────────────────────────────")
        print(f"  {'#':<6} {'Decoded':<10} {'Fidelity':<12} {'Status'}")
        print(f"  {'─'*45}")

    for i, state in enumerate(received_states):
        char, f, confirmed = decode_state(state, threshold, noise_tolerant)
        display = 'SPC' if char == ' ' else f"'{char}'"
        decoded_chars.append(char)
        decode_report.append((char, f, confirmed))

        if verbose:
            status = '✓' if confirmed else '✗ LOW FIDELITY'
            print(f"  {i+1:<6} {display:<10} {f:<12.6f} {status}")

    decoded_text = ''.join(decoded_chars)

    if verbose:
        print(f"\n  Decoded message: \"{decoded_text}\"")
        confirmed_count = sum(1 for _, _, c in decode_report if c)
        print(f"  Confirmed:  {confirmed_count}/{len(received_states)} characters")
        print(f"──────────────────────────────────────────────────────────────\n")

    return decoded_text, decode_report

# ── Inverse Gate Verification ──────────────────────────────────────────────────

def verify_via_inverse(received_state, char):
    """
    Secondary verification: apply inverse gate sequence and check for |0>.

    LOGIC:
      If 'char' is the correct decoding, then applying its inverse gates
      to the received state should return approximately |0>.
      Fidelity with |0> after inversion confirms the hypothesis.

      This is computationally more expensive than library lookup
      (requires applying gates) but provides independent confirmation.

    Args:
        received_state: qutrit state from Grid B
        char: hypothesized decoded character
    Returns:
        ground_fidelity: F(result, |0>) — should be ~1.0 if correct
    """
    inv_gates = build_inverse_sequence(char)
    result = apply_sequence(inv_gates, state=received_state.copy())
    return fidelity(result, ket_0)

# ── Noise Model ────────────────────────────────────────────────────────────────

def add_depolarizing_noise(state, sigma=0.05):
    """
    Simulate depolarizing noise on a qutrit state.
    Adds complex Gaussian perturbation and renormalizes.

    LOGIC:
      Real qutrit hardware (trapped ions, superconducting qutrits)
      introduces decoherence that perturbs the state vector.
      Model: |ψ_noisy> = normalize(|ψ> + σ·η) where η ~ CN(0,1)
      σ=0.01 → low noise (near-term hardware)
      σ=0.05 → moderate noise (current hardware)
      σ=0.10 → high noise (stress test)

    Args:
        state: ideal qutrit state vector
        sigma: noise level (standard deviation of perturbation)
    Returns:
        noisy_state: perturbed normalized state
    """
    noise = sigma * (np.random.randn(3) + 1j * np.random.randn(3))
    return normalize(state + noise)

def noise_robustness_test(text, sigma_levels=[0.01, 0.05, 0.10, 0.20]):
    """
    Test decoder robustness across noise levels.

    LOGIC:
      For each noise level σ, encode the text, add noise to each
      qutrit state, then attempt decoding with noise_tolerant=True.
      Report character accuracy rate at each noise level.
      This simulates real hardware fidelity degradation.

    Args:
        text: test string to encode and decode
        sigma_levels: list of noise standard deviations to test
    Returns:
        results: dict { sigma -> accuracy_rate }
    """
    print(f"\n── Noise Robustness Test: \"{text}\" ──────────────────────────")
    print(f"  {'Noise σ':<12} {'Accuracy':<12} {'Decoded'}")
    print(f"  {'─'*50}")

    encoded, _, _ = encode_string(text)
    results = {}

    for sigma in sigma_levels:
        noisy_states = []
        for char, state, cost in encoded:
            noisy = add_depolarizing_noise(state, sigma=sigma)
            noisy_states.append(noisy)

        decoded, report = decode_sequence(noisy_states, noise_tolerant=True, verbose=False)
        accuracy = sum(
            1 for (orig, _, _), (dec, _, conf) in zip(encoded, report)
            if orig == dec
        ) / len(encoded)

        results[sigma] = accuracy
        print(f"  σ={sigma:<10} {accuracy*100:<10.1f}%  \"{decoded}\"")

    print()
    return results

# ── Full Round-Trip Pipeline ───────────────────────────────────────────────────

def qchat_roundtrip(text, verbose_teleport=False, verbose_decode=True):
    """
    Complete QChat round-trip: encode → teleport → decode.
    Demonstrates the full pipeline from typed text to received text.

    LOGIC:
      1. Keyboard layer encodes text to qutrit states (Grid A)
      2. Teleportation protocol moves each state to Grid B
      3. Decoder identifies each received state via fidelity matching
      4. Reconstructed text compared to original for accuracy

    Args:
        text: original message string
        verbose_teleport: print teleportation protocol steps
        verbose_decode: print decoding trace
    Returns:
        decoded_text: reconstructed message
        accuracy: character-level accuracy (0.0 to 1.0)
    """
    print(f"\n{'═'*60}")
    print(f"  QChat Round-Trip: \"{text}\"")
    print(f"{'═'*60}")

    # ENCODE
    encoded, _, total_cost = encode_string(text)
    print(f"\n  [Grid A] Encoded {len(text)} characters ({total_cost} total gates)")

    # TELEPORT
    print(f"  [Channel] Teleporting qutrit sequence...")
    recovered_states = []
    fidelities = []
    for char, state, cost in encoded:
        recovered, f = teleport(state, verbose=verbose_teleport)
        recovered_states.append(recovered)
        fidelities.append(f)

    mean_teleport_fidelity = np.mean(fidelities)
    print(f"  [Channel] Mean teleport fidelity: {mean_teleport_fidelity:.6f}")

    # DECODE
    print(f"\n  [Grid B] Decoding received states...")
    decoded_text, decode_report = decode_sequence(
        recovered_states, verbose=verbose_decode
    )

    # ACCURACY
    correct = sum(1 for o, d in zip(text.lower(), decoded_text) if o == d)
    accuracy = correct / len(text)

    print(f"{'═'*60}")
    print(f"  Original:  \"{text.lower()}\"")
    print(f"  Decoded:   \"{decoded_text}\"")
    print(f"  Accuracy:  {accuracy*100:.1f}% ({correct}/{len(text)} chars)")
    print(f"{'═'*60}\n")

    return decoded_text, accuracy

# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("QChat — Decoder (Grid B)")
    print("Fidelity-based qutrit state discrimination | Nate Warner 2026\n")

    # Single state decode test
    print("── Single State Decode Tests ─────────────────────────────────")
    for char in ['e', 't', 'a', 's', 'z', ' ']:
        state, cost = char_to_state(char) if char != ' ' else (apply_sequence([]), 0)
        decoded, f, confirmed = decode_state(state)
        display = 'SPC' if char == ' ' else char
        print(f"  Encoded '{display}' → decoded '{decoded}' | F={f:.6f} | {'✓' if confirmed else '✗'}")

    # Inverse gate verification
    print("\n── Inverse Gate Verification ─────────────────────────────────")
    for char in ['e', 'n', 'q']:
        state, _ = char_to_state(char)
        gf = verify_via_inverse(state, char)
        print(f"  '{char}' inverse → ground fidelity F={gf:.6f} | {'✓' if gf > 0.999 else '✗'}")

    # Full round-trip tests
    qchat_roundtrip("hello")
    qchat_roundtrip("qchat")
    qchat_roundtrip("nate")

    # Noise robustness
    noise_robustness_test("the quick brown fox", sigma_levels=[0.01, 0.05, 0.10, 0.20])

    # Reference library summary
    print("── Reference Library Summary ─────────────────────────────────")
    print(f"  Total characters encoded: {len(REFERENCE_LIBRARY)}")
    tiers = {}
    for char, (gates, cost, desc) in CHAR_MAP.items():
        tiers[cost] = tiers.get(cost, 0) + 1
    for tier, count in sorted(tiers.items()):
        print(f"  Tier {tier} ({tier} gates): {count} characters")
