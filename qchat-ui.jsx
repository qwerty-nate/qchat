import { useState, useRef, useEffect } from "react";

const CHAR_TO_VEC = {
  'NULL':'0000',' ':'0001','e':'0002','t':'0010','a':'0011','o':'0012',
  'i':'0020','n':'0021','s':'0022','h':'0100','r':'0101','d':'0102',
  'l':'0110','c':'0111','u':'0112','m':'0120','w':'0121','f':'0122',
  'g':'0200','y':'0201','p':'0202','b':'1000','v':'1001','k':'1002',
  'j':'1010','x':'1011','q':'1012','z':'1020',
  '0':'1100','1':'1101','2':'1102','3':'1110','4':'1111','5':'1112',
  '6':'1120','7':'1121','8':'1122','9':'1200',
  '.':'1201',',':'1202','!':'2000','?':'2001',"'":'2002','"':'2010',
  '-':'2011','_':'2012','(':'2020',')':'2021','[':'2022',']':'2100',
  '{':'2101','}':'2102',':':'2110',';':'2111','/':'2112','\\':'2120',
  '@':'2121','#':'2122','$':'2200','%':'2201','&':'2202','*':'2210',
  '+':'2211','=':'2212','<':'2220','>':'2221','|':'2222',
  '~':'0210','^':'0211','`':'0212',
};
const VEC_TO_CHAR = Object.fromEntries(Object.entries(CHAR_TO_VEC).map(([k,v])=>[v,k]));

const SIGNALS = { WRITE:'110', SEND:'112', RECEIVE:'101', READ:'121', STORE:'111' };

function encodeChar(char, senderName) {
  const vec = CHAR_TO_VEC[char] || CHAR_TO_VEC[' '];
  return {
    char,
    vec,
    ops: [
      { signal: 'WRITE',   ijk: SIGNALS.WRITE,   bcde: vec, client: senderName },
      { signal: 'SEND',    ijk: SIGNALS.SEND,    bcde: vec, client: senderName },
      { signal: 'RECEIVE', ijk: SIGNALS.RECEIVE, bcde: vec, client: senderName === 'Alice' ? 'Bob' : 'Alice' },
      { signal: 'READ',    ijk: SIGNALS.READ,    bcde: vec, client: senderName === 'Alice' ? 'Bob' : 'Alice' },
      { signal: 'STORE',   ijk: SIGNALS.STORE,   bcde: vec, client: senderName === 'Alice' ? 'Bob' : 'Alice' },
    ]
  };
}

function encodeMessage(text, senderName) {
  return text.split('').map(c => encodeChar(CHAR_TO_VEC[c] ? c : ' ', senderName));
}

const SIGNAL_COLORS = {
  WRITE:   '#4f8ef7',
  SEND:    '#a78bfa',
  RECEIVE: '#34d399',
  READ:    '#fbbf24',
  STORE:   '#f472b6',
};

export default function App() {
  const [messages, setMessages] = useState([]);
  const [aliceInput, setAliceInput] = useState('');
  const [bobInput, setBobInput] = useState('');
  const [activeOps, setActiveOps] = useState([]);
  const [sending, setSending] = useState(null);
  const logRef = useRef(null);
  const chatRef = useRef(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [activeOps]);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages]);

  async function sendMessage(sender, text) {
    if (!text.trim() || sending) return;
    const recipient = sender === 'Alice' ? 'Bob' : 'Alice';
    setSending(sender);
    setActiveOps([]);

    const encoded = encodeMessage(text.toLowerCase(), sender);
    const allOps = [];

    for (const { char, ops } of encoded) {
      for (const op of ops) {
        allOps.push(op);
        setActiveOps(prev => [...prev, op]);
        await new Promise(r => setTimeout(r, 60));
      }
    }

    setMessages(prev => [...prev, {
      id: Date.now(),
      sender,
      recipient,
      text: text.toLowerCase(),
      ops: allOps,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }]);

    if (sender === 'Alice') setAliceInput('');
    else setBobInput('');
    setSending(null);
  }

  function handleKey(sender, e) {
    if (e.key === 'Enter') sendMessage(sender, sender === 'Alice' ? aliceInput : bobInput);
  }

  const aliceMsgs = messages.filter(m => m.sender === 'Alice');
  const bobMsgs   = messages.filter(m => m.sender === 'Bob');

  return (
    <div style={{
      fontFamily: "'IBM Plex Mono', monospace",
      background: '#0a0a0f',
      minHeight: '100vh',
      color: '#e2e8f0',
      padding: '0',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{
        borderBottom: '1px solid #1e2030',
        padding: '14px 24px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        background: '#0d0d14',
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: '#4f8ef7',
          boxShadow: '0 0 8px #4f8ef7',
        }} />
        <span style={{ fontSize: 13, color: '#64748b', letterSpacing: '0.1em' }}>
          QUTRIT CHAT — SIMULATED CHANNEL
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 16 }}>
          {Object.entries(SIGNAL_COLORS).map(([sig, col]) => (
            <span key={sig} style={{ fontSize: 11, color: col, letterSpacing: '0.05em' }}>
              {sig}
            </span>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', height: 'calc(100vh - 53px)' }}>

        {/* Alice panel */}
        <div style={{
          width: '28%', borderRight: '1px solid #1e2030',
          display: 'flex', flexDirection: 'column', background: '#0d0d14',
        }}>
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid #1e2030',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%',
              background: '#1a2040', border: '1px solid #4f8ef7',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, color: '#4f8ef7', fontWeight: 600,
            }}>A</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 500 }}>Alice</div>
              <div style={{ fontSize: 10, color: '#475569' }}>member_id=1</div>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {aliceMsgs.map(m => (
              <div key={m.id} style={{
                background: '#131825', border: '1px solid #1e2a40',
                borderRadius: 6, padding: '8px 10px',
              }}>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>
                  → Bob · {m.time}
                </div>
                <div style={{ fontSize: 13 }}>{m.text}</div>
              </div>
            ))}
            {messages.filter(m => m.recipient === 'Alice').map(m => (
              <div key={m.id + 'r'} style={{
                background: '#0f1a14', border: '1px solid #1a3020',
                borderRadius: 6, padding: '8px 10px',
              }}>
                <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                  ← Bob · {m.time}
                </div>
                <div style={{ fontSize: 13, color: '#86efac' }}>{m.text}</div>
              </div>
            ))}
          </div>
          <div style={{ padding: '12px 16px', borderTop: '1px solid #1e2030' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={aliceInput}
                onChange={e => setAliceInput(e.target.value)}
                onKeyDown={e => handleKey('Alice', e)}
                placeholder="alice types..."
                disabled={!!sending}
                style={{
                  flex: 1, background: '#131825', border: '1px solid #1e2a40',
                  borderRadius: 4, padding: '7px 10px', fontSize: 12,
                  color: '#e2e8f0', outline: 'none',
                  opacity: sending ? 0.5 : 1,
                  fontFamily: "'IBM Plex Mono', monospace",
                }}
              />
              <button
                onClick={() => sendMessage('Alice', aliceInput)}
                disabled={!!sending || !aliceInput.trim()}
                style={{
                  background: sending === 'Alice' ? '#1e2a40' : '#1a2540',
                  border: '1px solid #4f8ef7', borderRadius: 4,
                  color: '#4f8ef7', fontSize: 11, padding: '0 12px',
                  cursor: sending || !aliceInput.trim() ? 'not-allowed' : 'pointer',
                  opacity: !aliceInput.trim() ? 0.4 : 1,
                  fontFamily: "'IBM Plex Mono', monospace",
                }}
              >
                SEND
              </button>
            </div>
          </div>
        </div>

        {/* Operation log */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          background: '#080810',
        }}>
          <div style={{
            padding: '10px 16px', borderBottom: '1px solid #1e2030',
            fontSize: 11, color: '#475569', letterSpacing: '0.08em',
          }}>
            QUANTUM CHANNEL · OPERATION LOG
          </div>
          <div
            ref={logRef}
            style={{
              flex: 1, overflowY: 'auto', padding: '12px 16px',
              display: 'flex', flexDirection: 'column', gap: 4,
            }}
          >
            {activeOps.length === 0 && (
              <div style={{
                color: '#2d3748', fontSize: 12, textAlign: 'center',
                marginTop: '40%', letterSpacing: '0.1em',
              }}>
                awaiting transmission...
              </div>
            )}
            {activeOps.map((op, idx) => (
              <div key={idx} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                fontSize: 11, padding: '3px 0',
                borderBottom: '1px solid #0f1020',
                animation: 'fadeIn 0.15s ease',
              }}>
                <span style={{
                  color: SIGNAL_COLORS[op.signal],
                  minWidth: 64, fontWeight: 500,
                }}>{op.signal}</span>
                <span style={{ color: '#475569', minWidth: 60 }}>{op.client}</span>
                <span style={{ color: '#334155' }}>ijk=</span>
                <span style={{ color: '#94a3b8' }}>{op.ijk}</span>
                <span style={{ color: '#334155', marginLeft: 8 }}>bcde=</span>
                <span style={{ color: '#cbd5e1' }}>{op.bcde}</span>
                <span style={{ color: '#1e3050', marginLeft: 8 }}>
                  {VEC_TO_CHAR[op.bcde] || '?'}
                </span>
              </div>
            ))}
          </div>

          {/* Conversation log at bottom */}
          <div style={{
            borderTop: '1px solid #1e2030', padding: '10px 16px',
            maxHeight: 120, overflowY: 'auto',
          }} ref={chatRef}>
            <div style={{ fontSize: 10, color: '#475569', marginBottom: 6, letterSpacing: '0.08em' }}>
              CONVERSATION
            </div>
            {messages.map(m => (
              <div key={m.id} style={{ fontSize: 12, marginBottom: 3 }}>
                <span style={{ color: m.sender === 'Alice' ? '#4f8ef7' : '#a78bfa' }}>
                  {m.sender}
                </span>
                <span style={{ color: '#475569' }}> → </span>
                <span style={{ color: m.sender === 'Alice' ? '#a78bfa' : '#4f8ef7' }}>
                  {m.recipient}
                </span>
                <span style={{ color: '#64748b' }}>: </span>
                <span style={{ color: '#e2e8f0' }}>{m.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Bob panel */}
        <div style={{
          width: '28%', borderLeft: '1px solid #1e2030',
          display: 'flex', flexDirection: 'column', background: '#0d0d14',
        }}>
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid #1e2030',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%',
              background: '#1a1040', border: '1px solid #a78bfa',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, color: '#a78bfa', fontWeight: 600,
            }}>B</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 500 }}>Bob</div>
              <div style={{ fontSize: 10, color: '#475569' }}>member_id=2</div>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {bobMsgs.map(m => (
              <div key={m.id} style={{
                background: '#13101f', border: '1px solid #2a1e40',
                borderRadius: 6, padding: '8px 10px',
              }}>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>
                  → Alice · {m.time}
                </div>
                <div style={{ fontSize: 13 }}>{m.text}</div>
              </div>
            ))}
            {messages.filter(m => m.recipient === 'Bob').map(m => (
              <div key={m.id + 'r'} style={{
                background: '#0f1218', border: '1px solid #1e2535',
                borderRadius: 6, padding: '8px 10px',
              }}>
                <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                  ← Alice · {m.time}
                </div>
                <div style={{ fontSize: 13, color: '#93c5fd' }}>{m.text}</div>
              </div>
            ))}
          </div>
          <div style={{ padding: '12px 16px', borderTop: '1px solid #1e2030' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={bobInput}
                onChange={e => setBobInput(e.target.value)}
                onKeyDown={e => handleKey('Bob', e)}
                placeholder="bob types..."
                disabled={!!sending}
                style={{
                  flex: 1, background: '#13101f', border: '1px solid #2a1e40',
                  borderRadius: 4, padding: '7px 10px', fontSize: 12,
                  color: '#e2e8f0', outline: 'none',
                  opacity: sending ? 0.5 : 1,
                  fontFamily: "'IBM Plex Mono', monospace",
                }}
              />
              <button
                onClick={() => sendMessage('Bob', bobInput)}
                disabled={!!sending || !bobInput.trim()}
                style={{
                  background: sending === 'Bob' ? '#2a1e40' : '#1e1535',
                  border: '1px solid #a78bfa', borderRadius: 4,
                  color: '#a78bfa', fontSize: 11, padding: '0 12px',
                  cursor: sending || !bobInput.trim() ? 'not-allowed' : 'pointer',
                  opacity: !bobInput.trim() ? 0.4 : 1,
                  fontFamily: "'IBM Plex Mono', monospace",
                }}
              >
                SEND
              </button>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(2px); } to { opacity: 1; transform: none; } }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #1e2030; border-radius: 2px; }
      `}</style>
    </div>
  );
}