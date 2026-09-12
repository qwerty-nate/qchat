import cirq

# ── Encoding library ──────────────────────────────────────────────────────────
# Canonical 81-state scheme -- same SYMBOLS ordering (NULL, SPACE, letters by
# frequency, digits, punctuation, extras) and same index -> 4-trit base-3
# encoding as char_to_trits()/SYMBOLS in qchat_payload_circuit.py, which
# qchat_full_chain.py and index.html's CHARSET also derive from. Previously
# this table used its own non-contiguous vectors and swapped in BS/DEL/ESC
# where the canonical scheme has §/¶/•/°/©/®/™/€/£ -- both have been dropped
# in favor of matching the shared encoding exactly.
CHAR_TO_VEC = {
    'NULL': '0000', ' ':    '0001',
    'e':    '0002', 't':    '0010', 'a':    '0011', 'o':    '0012',
    'i':    '0020', 'n':    '0021', 's':    '0022', 'h':    '0100',
    'r':    '0101', 'd':    '0102', 'l':    '0110', 'c':    '0111',
    'u':    '0112', 'm':    '0120', 'w':    '0121', 'f':    '0122',
    'g':    '0200', 'y':    '0201', 'p':    '0202', 'b':    '0210',
    'v':    '0211', 'k':    '0212', 'j':    '0220', 'x':    '0221',
    'q':    '0222', 'z':    '1000',
    '0':    '1001', '1':    '1002', '2':    '1010', '3':    '1011',
    '4':    '1012', '5':    '1020', '6':    '1021', '7':    '1022',
    '8':    '1100', '9':    '1101',
    '.':    '1102', ',':    '1110',
    '!':    '1111', '?':    '1112', "'":    '1120', '"':    '1121',
    ';':    '1122', ':':    '1200', '-':    '1201', '_':    '1202',
    '(':    '1210', ')':    '1211', '[':    '1212', ']':    '1220',
    '{':    '1221', '}':    '1222', '<':    '2000', '>':    '2001',
    '/':    '2002', '\\':   '2010', '|':    '2011', '@':    '2012',
    '#':    '2020', '$':    '2021', '%':    '2022', '^':    '2100',
    '&':    '2101', '*':    '2102', '+':    '2110', '=':    '2111',
    '~':    '2112', '`':    '2120',
    'NL':   '2121', 'TAB':  '2122',
    '§':    '2200', '¶':    '2201', '•':    '2202', '°':    '2210',
    '©':    '2211', '®':    '2212', '™':    '2220', '€':    '2221',
    '£':    '2222',
}
VEC_TO_CHAR = {v: k for k, v in CHAR_TO_VEC.items()}

# ── Signals ───────────────────────────────────────────────────────────────────
# Confirmed IJK tree (forward-only, single-qutrit-flip transitions, cyclic
# mod-3) -- canonical source: qchat_full_chain.py STATES dict. Pulled in here
# so this simplified client's ijk vectors stay in sync with the real tree
# instead of drifting (READ and STORE previously disagreed with it, and plain
# SEND was a stand-in for the herald/ack sub-states below).
OFF                = [0, 0, 0]   # 000
ON_SCAN            = [1, 0, 0]   # 100
WRITE              = [1, 1, 0]   # 110
ENCRYPT            = [1, 1, 1]   # 111
SEND_ATTEMPT       = [2, 1, 1]   # 211 -- photon emitted, BSM in flight
SEND_HERALD_OK     = [2, 2, 1]   # 221 -- BSM heralded success (send-side ack)
SEND_COMPLETE      = [2, 2, 2]   # 222 -- correction bits transmitted, send done
RECEIVE            = [1, 0, 1]   # 101
AWAITING_ACK_RECV  = [2, 0, 1]   # 201 -- waiting on classical correction bits
RECEIVE_CONFIRMED  = [0, 0, 1]   # 001 -- correction bits received
DECRYPT            = [0, 1, 1]   # 011
READ               = [0, 1, 2]   # 012
STORE              = [1, 1, 2]   # 112
DELETE             = [1, 2, 2]   # 122

# Herald failure branch -- not yet wired into send() below. Real behavior
# would retry from SEND_ATTEMPT instead of advancing to SEND_COMPLETE.
SEND_HERALD_FAIL   = [2, 1, 2]   # 212

# ── Client class ──────────────────────────────────────────────────────────────
class QutritClient:
    def __init__(self, name, member_id):
        self.name = name
        self.member_id = member_id  # value for 'a' qutrit: 0, 1, or 2
        self.buffer = []
        self.channel = None  # set after both clients created

        # State machine qutrits
        self.i = cirq.NamedQid(f'i_{name}', dimension=3)
        self.j = cirq.NamedQid(f'j_{name}', dimension=3)
        self.k = cirq.NamedQid(f'k_{name}', dimension=3)

        # Data register qutrits (a holds member_id, bcde hold character)
        self.a = cirq.NamedQid(f'a_{name}', dimension=3)
        self.b = cirq.NamedQid(f'b_{name}', dimension=3)
        self.c = cirq.NamedQid(f'c_{name}', dimension=3)
        self.d = cirq.NamedQid(f'd_{name}', dimension=3)
        self.e = cirq.NamedQid(f'e_{name}', dimension=3)

        self.sim = cirq.Simulator()

    def _reset(self):
        return cirq.Circuit(
            cirq.reset(self.i), cirq.reset(self.j), cirq.reset(self.k),
            cirq.reset(self.a), cirq.reset(self.b),
            cirq.reset(self.c), cirq.reset(self.d), cirq.reset(self.e)
        )

    def _set_ijk(self, signal):
        gates = []
        for qutrit, val in zip([self.i, self.j, self.k], signal):
            if val != 0:
                gates.append(cirq.XPowGate(dimension=3, exponent=val).on(qutrit))
        return gates

    def _set_a(self): #Assigns member_id to conversation participant via qutrit a
        """Load member_id into a qutrit."""
        if self.member_id != 0:
            return [cirq.XPowGate(dimension=3, exponent=self.member_id).on(self.a)]
        return []

    def _load_vec_to_bcde(self, vec, control_signal):
        gates = []
        for qutrit, val in zip([self.b, self.c, self.d, self.e], vec):
            val = int(val)
            if val != 0:
                gates.append(
                    cirq.XPowGate(dimension=3, exponent=val).on(qutrit)
                        .controlled_by(self.i, self.j, self.k,
                                       control_values=control_signal)
                )
        return gates

    def _run(self, gates, label):
        circuit = cirq.Circuit(
            self._reset(),
            *gates,
            cirq.measure(self.i, self.j, self.k, self.a,
                         self.b, self.c, self.d, self.e)
        )
        result = self.sim.run(circuit, repetitions=1)
        vector = ''.join(str(v[0]) for v in result.measurements.values())
        vector = vector.replace(' ', '').replace('[', '').replace(']', '')
        ijk  = vector[0:3]
        a    = vector[3]
        bcde = vector[4:8]
        print(f"  [{self.name}] {label}")
        print(f"    ijk={ijk}  a={a}  bcde={bcde}")
        return ijk, a, bcde

    # ── Operations ────────────────────────────────────────────────────────────
    def write(self, char):
        """WRITE (110): compose a character into bcde."""
        vec = CHAR_TO_VEC.get(char)
        if vec is None:
            raise ValueError(f"'{char}' not in encoding library")
        gates = self._set_ijk(WRITE) + self._set_a() + \
                self._load_vec_to_bcde(vec, WRITE)
        _, _, bcde = self._run(gates, f"WRITE '{char}'")
        return bcde

    def send(self, bcde_vec):
        """SEND_ATTEMPT (211): transfer bcde vector to the other client's RECEIVE.

        NOTE: this collapses straight to a transfer, same as before -- the
        SEND_HERALD_OK/SEND_COMPLETE handshake from the confirmed tree isn't
        simulated here yet (see qchat_full_chain.py for that placeholder walk).
        """
        gates = self._set_ijk(SEND_ATTEMPT) + self._set_a()
        for qutrit, val in zip([self.b, self.c, self.d, self.e], bcde_vec):
            val = int(val)
            if val != 0:
                gates.append(cirq.XPowGate(dimension=3, exponent=val).on(qutrit))
        _, _, bcde = self._run(gates, f"SEND_ATTEMPT  vec={bcde_vec}")
        # Transfer vector over the simulated channel
        self.channel.receive(bcde_vec, sender_id=self.member_id)

    def receive(self, bcde_vec, sender_id):
        """RECEIVE (101): accept incoming vector into bcde."""
        gates = self._set_ijk(RECEIVE) + self._set_a() + \
                self._load_vec_to_bcde(bcde_vec, RECEIVE)
        _, _, bcde = self._run(gates, f"RECEIVE vec={bcde_vec} from member={sender_id}")
        return bcde

    def read(self, bcde_vec):
        """READ (012): decode bcde vector to character."""
        gates = self._set_ijk(READ) + self._set_a()
        for qutrit, val in zip([self.b, self.c, self.d, self.e], bcde_vec):
            val = int(val)
            if val != 0:
                gates.append(cirq.XPowGate(dimension=3, exponent=val).on(qutrit))
        _, _, result_vec = self._run(gates, f"READ  vec={bcde_vec}")
        char = VEC_TO_CHAR.get(result_vec, '?')
        print(f"    char='{char}'")
        return char

    def store(self, bcde_vec):
        """STORE (112): commit character to buffer."""
        char = VEC_TO_CHAR.get(bcde_vec, '?')
        self.buffer.append(char)
        print(f"  [{self.name}] STORE '{char}' → buffer: {''.join(self.buffer)}")
        return char

    def dispatch(self, signal, char=None, bcde_vec=None):
        if signal == 'WRITE':   return self.write(char)
        elif signal == 'SEND':  return self.send(bcde_vec)
        elif signal == 'READ':  return self.read(bcde_vec)
        elif signal == 'STORE': return self.store(bcde_vec)
        else: raise ValueError(f"Unknown signal '{signal}'")

# ── Channel ───────────────────────────────────────────────────────────────────
class QuantumChannel:
    """Simulated channel connecting two QutritClients."""
    def __init__(self, client_a, client_b):
        self.client_a = client_a
        self.client_b = client_b
        client_a.channel = self
        client_b.channel = self

    def receive(self, bcde_vec, sender_id):
        """Route incoming vector to the correct recipient."""
        recipient = self.client_b if sender_id == self.client_a.member_id \
                    else self.client_a
        bcde = recipient.receive(bcde_vec, sender_id)
        char = recipient.read(bcde)
        recipient.store(bcde)


# ── Demo ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("═" * 50)
    print(" Qutrit chat simulation")
    print("═" * 50)

    # Create two clients with distinct member IDs
    alice = QutritClient('alice', member_id=1)
    bob   = QutritClient('bob',   member_id=2)
    message_alice = input("Alice, enter your message: ")
    message_bob = input("Bob, enter your message: ")

    # Connect via shared channel
    channel = QuantumChannel(alice, bob)

    # Alice sends "hi" to Bob
    print(f"\n── Alice → Bob: {message_alice} ──────────────────────────")
    for char in message_alice:
        vec = alice.write(char)
        alice.send(vec)

    # Bob sends "hey" back to Alice
    print(f"\n── Bob → Alice: {message_bob} ─────────────────────────")
    for char in message_bob:
        vec = bob.write(char)
        bob.send(vec)

    # Final buffers
    print("\n── Conversation ────────────────────────────────")
    print(f"  Alice received : '{''.join(alice.buffer)}'")
    print(f"  Bob   received : '{''.join(bob.buffer)}'")
