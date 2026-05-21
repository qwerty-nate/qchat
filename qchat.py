import cirq

# ── Encoding library ──────────────────────────────────────────────────────────
CHAR_TO_VEC = {
    'NULL': '0000', ' ':    '0001',
    'e':    '0002', 't':    '0010', 'a':    '0011', 'o':    '0012',
    'i':    '0020', 'n':    '0021', 's':    '0022', 'h':    '0100',
    'r':    '0101', 'd':    '0102', 'l':    '0110', 'c':    '0111',
    'u':    '0112', 'm':    '0120', 'w':    '0121', 'f':    '0122',
    'g':    '0200', 'y':    '0201', 'p':    '0202', 'b':    '1000',
    'v':    '1001', 'k':    '1002', 'j':    '1010', 'x':    '1011',
    'q':    '1012', 'z':    '1020',
    '0':    '1100', '1':    '1101', '2':    '1102', '3':    '1110',
    '4':    '1111', '5':    '1112', '6':    '1120', '7':    '1121',
    '8':    '1122', '9':    '1200',
    '.':    '1201', ',':    '1202',
    '!':    '2000', '?':    '2001', "'":    '2002', '"':    '2010',
    '-':    '2011', '_':    '2012', '(':    '2020', ')':    '2021',
    '[':    '2022', ']':    '2100', '{':    '2101', '}':    '2102',
    ':':    '2110', ';':    '2111', '/':    '2112', '\\':   '2120',
    '@':    '2121', '#':    '2122', '$':    '2200', '%':    '2201',
    '&':    '2202', '*':    '2210', '+':    '2211', '=':    '2212',
    '<':    '2220', '>':    '2221', '|':    '2222',
    '~':    '0210', '^':    '0211', '`':    '0212',
    'NL':   '0220', 'TAB':  '0221', 'BS':   '0222',
    'DEL':  '1021', 'ESC':  '1022',
}
VEC_TO_CHAR = {v: k for k, v in CHAR_TO_VEC.items()}

# ── Signals ───────────────────────────────────────────────────────────────────
WRITE   = [1, 1, 0]   # 110
RECEIVE = [1, 0, 1]   # 101
READ    = [1, 2, 1]   # 121
STORE   = [1, 1, 1]   # 111
SEND    = [1, 1, 2]   # 112

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

    def _set_a(self):
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
        """SEND (112): transfer bcde vector to the other client's RECEIVE."""
        gates = self._set_ijk(SEND) + self._set_a()
        for qutrit, val in zip([self.b, self.c, self.d, self.e], bcde_vec):
            val = int(val)
            if val != 0:
                gates.append(cirq.XPowGate(dimension=3, exponent=val).on(qutrit))
        _, _, bcde = self._run(gates, f"SEND  vec={bcde_vec}")
        # Transfer vector over the simulated channel
        self.channel.receive(bcde_vec, sender_id=self.member_id)

    def receive(self, bcde_vec, sender_id):
        """RECEIVE (101): accept incoming vector into bcde."""
        gates = self._set_ijk(RECEIVE) + self._set_a() + \
                self._load_vec_to_bcde(bcde_vec, RECEIVE)
        _, _, bcde = self._run(gates, f"RECEIVE vec={bcde_vec} from member={sender_id}")
        return bcde

    def read(self, bcde_vec):
        """READ (121): decode bcde vector to character."""
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
        """STORE (111): commit character to buffer."""
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
