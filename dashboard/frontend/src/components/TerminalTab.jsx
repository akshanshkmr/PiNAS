import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { Badge, Panel } from './ui'

const THEME = {
  background: '#060a12',
  foreground: '#dbe4f2',
  cursor: '#60a5fa',
  cursorAccent: '#060a12',
  selectionBackground: '#25406e',
  black: '#0d1626',
  red: '#ff6b6b',
  green: '#35d6a4',
  yellow: '#f5b544',
  blue: '#60a5fa',
  magenta: '#a78bfa',
  cyan: '#5ee0d0',
  white: '#dbe4f2',
  brightBlack: '#6b7d9e',
}

export default function TerminalTab() {
  const hostRef = useRef(null)
  const [status, setStatus] = useState('connecting')

  useEffect(() => {
    const term = new Terminal({
      fontFamily: "'Space Mono', ui-monospace, monospace",
      fontSize: 13,
      lineHeight: 1.2,
      cursorBlink: true,
      theme: THEME,
      scrollback: 5000,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(hostRef.current)

    // Fit needs a laid-out container; do it on the next frame.
    const doFit = () => {
      try {
        fit.fit()
      } catch {
        /* container not measurable yet */
      }
    }
    requestAnimationFrame(doFit)

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/api/terminal`)
    ws.binaryType = 'arraybuffer'
    const decoder = new TextDecoder()

    const sendResize = () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      }
    }

    ws.onopen = () => {
      setStatus('connected')
      doFit()
      sendResize()
      term.focus()
    }
    ws.onmessage = (e) => {
      term.write(typeof e.data === 'string' ? e.data : decoder.decode(e.data))
    }
    ws.onclose = () => {
      setStatus('closed')
      term.write('\r\n\x1b[38;5;203m● session ended — switch tabs and back to reconnect\x1b[0m\r\n')
    }
    ws.onerror = () => setStatus('closed')

    const dataSub = term.onData((d) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', data: d }))
    })
    const resizeSub = term.onResize(sendResize)

    const onWinResize = () => doFit()
    window.addEventListener('resize', onWinResize)

    return () => {
      window.removeEventListener('resize', onWinResize)
      dataSub.dispose()
      resizeSub.dispose()
      ws.close()
      term.dispose()
    }
  }, [])

  const tone = status === 'connected' ? 'ok' : status === 'closed' ? 'crit' : 'warn'

  return (
    <div className="stack">
      <Panel
        label="terminal"
        meta="login shell · runs as your user"
        actions={<Badge tone={tone}>{status}</Badge>}
      >
        <p className="field-hint terminal-note">
          A full bash session on the Pi, running as your Linux account. `sudo` works without a password — the same
          power as an SSH login, so treat it accordingly.
        </p>
        <div className="terminal-host" ref={hostRef} />
      </Panel>
    </div>
  )
}
