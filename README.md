qchat
A simulated qutrit-based (3-level quantum system) messaging architecture built in Cirq, exploring how ternary state machines could underpin real communication hardware.

Demo live at https://qchat-alpha.vercel.app/

What's in here:

	•	An 8-state hardware-inspired control register (IJK) with a verified single-qutrit-flip adjacency property across every transition
	•	An 81-state ternary character encoding scheme
	•	A full messaging pipeline (WRITE → ENCRYPT → SEND → RECEIVE → DECRYPT → READ → STORE → DELETE) between two independent simulated parties, with no entanglement crossing between them
	•	A working entanglement-based quantum key distribution (QKD) protocol — qutrit Bell pairs, two conjugate measurement bases, sifting, and QBER-based eavesdropper detection, verified empirically against an intercept-resend attack model
	•	Hardware-noise modeling (amplitude damping) distinguishing generic decoherence from an isolated bad qubit
	•	Supporting visualization and documentation tooling

The QKD protocol is functionally load-bearing: it produces a real, non-classical security guarantee, an eavesdropper is detectable via measurement disturbance.

Stack: Python, Cirq, NumPy, Matplotlib

Status: simulation-only; real quantum hardware would introduce gate error into the deterministic parts of this system.
