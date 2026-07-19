import { useCallback, useEffect, useRef, useState } from 'react'
import { api, fmtBytes } from '../api'
import { toast } from '../toast'
import { Badge, Btn, EmptyState, Field, Panel, Toggle } from './ui'

const GALLERY_KINDS = ['image', 'video', 'audio']

const RAW = (p) => `/api/files/raw?path=${encodeURIComponent(p)}`
const DOWNLOAD = (p) => `/api/files/download?path=${encodeURIComponent(p)}`
const THUMB = (p, s = 240) => `/api/files/thumb?path=${encodeURIComponent(p)}&size=${s}`

const THUMB_KINDS = new Set(['image', 'video'])
const VIEW_KEY = 'pinas.files.view'

const KIND_GLYPH = { image: '▧', video: '▶', audio: '♪', text: '≡', file: '·' }

/** Small SVG icons used on action buttons. currentColor so they inherit tone. */
function Icon({ name }) {
  const p = {
    className: 'btn-icon',
    viewBox: '0 0 16 16',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.5,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  }
  switch (name) {
    case 'upload':
      return (
        <svg {...p}>
          <path d="M8 11V3" />
          <polyline points="4.5 6.5 8 3 11.5 6.5" />
          <path d="M2.5 12v1.5A1.5 1.5 0 0 0 4 15h8a1.5 1.5 0 0 0 1.5-1.5V12" />
        </svg>
      )
    case 'download':
      return (
        <svg {...p}>
          <path d="M8 3v8" />
          <polyline points="4.5 7.5 8 11 11.5 7.5" />
          <path d="M2.5 12v1.5A1.5 1.5 0 0 0 4 15h8a1.5 1.5 0 0 0 1.5-1.5V12" />
        </svg>
      )
    case 'new-folder':
      return (
        <svg {...p}>
          <path d="M1.8 4.3a1 1 0 0 1 1-1h3.1l1.4 1.5h6.4a1 1 0 0 1 1 1v6.4a1 1 0 0 1-1 1H2.8a1 1 0 0 1-1-1z" />
          <line x1="8" y1="7.4" x2="8" y2="11" />
          <line x1="6.2" y1="9.2" x2="9.8" y2="9.2" />
        </svg>
      )
    case 'trash':
      return (
        <svg {...p}>
          <polyline points="2.5 4 13.5 4" />
          <path d="M4 4v9a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4" />
          <path d="M6 4V2.6a.6.6 0 0 1 .6-.6h2.8a.6.6 0 0 1 .6.6V4" />
          <line x1="6.8" y1="6.5" x2="6.8" y2="11.5" />
          <line x1="9.2" y1="6.5" x2="9.2" y2="11.5" />
        </svg>
      )
    case 'check':
      return (
        <svg {...p}>
          <polyline points="3 8.5 6.5 12 13 4.5" />
        </svg>
      )
    case 'x':
      return (
        <svg {...p}>
          <line x1="4" y1="4" x2="12" y2="12" />
          <line x1="12" y1="4" x2="4" y2="12" />
        </svg>
      )
    case 'up':
      return (
        <svg {...p}>
          <polyline points="4.5 8 8 4.5 11.5 8" />
          <line x1="8" y1="4.5" x2="8" y2="12" />
        </svg>
      )
    case 'refresh':
      return (
        <svg {...p}>
          <path d="M13 4v3H10" />
          <path d="M3 8a5 5 0 0 1 9-3l1 2" />
          <path d="M3 12v-3h3" />
          <path d="M13 8a5 5 0 0 1-9 3l-1-2" />
        </svg>
      )
    case 'list-view':
      return (
        <svg {...p}>
          <line x1="4.5" y1="4" x2="14" y2="4" />
          <line x1="4.5" y1="8" x2="14" y2="8" />
          <line x1="4.5" y1="12" x2="14" y2="12" />
          <circle cx="2" cy="4" r="0.7" fill="currentColor" stroke="none" />
          <circle cx="2" cy="8" r="0.7" fill="currentColor" stroke="none" />
          <circle cx="2" cy="12" r="0.7" fill="currentColor" stroke="none" />
        </svg>
      )
    case 'grid-view':
      return (
        <svg {...p}>
          <rect x="2" y="2" width="5" height="5" rx="0.5" />
          <rect x="9" y="2" width="5" height="5" rx="0.5" />
          <rect x="2" y="9" width="5" height="5" rx="0.5" />
          <rect x="9" y="9" width="5" height="5" rx="0.5" />
        </svg>
      )
    case 'play':
      return (
        <svg {...p} fill="currentColor" stroke="none">
          <polygon points="4.5 3 12.5 8 4.5 13" />
        </svg>
      )
    case 'share':
      return (
        <svg {...p}>
          <circle cx="12" cy="3.5" r="1.8" />
          <circle cx="4" cy="8" r="1.8" />
          <circle cx="12" cy="12.5" r="1.8" />
          <line x1="5.5" y1="7.1" x2="10.5" y2="4.4" />
          <line x1="5.5" y1="8.9" x2="10.5" y2="11.6" />
        </svg>
      )
    default:
      return null
  }
}

function ShareDialog({ entry, onClose }) {
  const [ttl, setTtl] = useState('86400')
  const [password, setPassword] = useState('')
  const [publicOn, setPublicOn] = useState(false)
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const [existing, setExisting] = useState([])
  const [copyState, setCopyState] = useState('')

  useEffect(() => {
    api('/shares').then((d) => setExisting(d.shares.filter((s) => s.path === entry.path)))
      .catch(() => {})
  }, [entry.path])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function create() {
    setBusy(true)
    try {
      const res = await api('/shares', {
        method: 'POST',
        body: {
          path: entry.path,
          ttl_seconds: ttl === '0' ? null : Number(ttl),
          mode: 'view',
          public: publicOn,
          password: password || null,
          label: entry.name,
        },
      })
      setCreated(res.share)
      setExisting((prev) => [res.share, ...prev])
      toast.ok('Share link created')
    } catch (err) {
      toast.err(err.detail)
    } finally {
      setBusy(false)
    }
  }

  async function revoke(token) {
    try {
      await api(`/shares/${token}`, { method: 'DELETE' })
      setExisting((prev) => prev.filter((s) => s.token !== token))
      if (created?.token === token) setCreated(null)
      toast.ok('Share revoked')
    } catch (err) {
      toast.err(err.detail)
    }
  }

  function shareUrl(s) {
    return `${window.location.origin}${s.url_path}`
  }

  async function copy(url) {
    try {
      await navigator.clipboard.writeText(url)
      setCopyState('copied')
      setTimeout(() => setCopyState(''), 1400)
    } catch {
      setCopyState('select')
    }
  }

  return (
    <div className="preview-overlay" onClick={onClose}>
      <div className="preview-box share-box" onClick={(e) => e.stopPropagation()}>
        <span className="tick tick-tl" aria-hidden="true" />
        <span className="tick tick-tr" aria-hidden="true" />
        <span className="tick tick-bl" aria-hidden="true" />
        <span className="tick tick-br" aria-hidden="true" />
        <header className="preview-head">
          <span className="mono preview-name">Share · {entry.name}</span>
          <Btn variant="ghost" onClick={onClose}>Close</Btn>
        </header>
        <div className="share-body">
          {!created && (
            <div className="stack">
              <Field label="Expires">
                <select className="input" value={ttl} onChange={(e) => setTtl(e.target.value)}>
                  <option value="3600">In 1 hour</option>
                  <option value="86400">In 24 hours</option>
                  <option value="604800">In 7 days</option>
                  <option value="2592000">In 30 days</option>
                  <option value="0">Never</option>
                </select>
              </Field>
              <Field label="Password (optional)">
                <input
                  className="input mono"
                  type="password"
                  value={password}
                  placeholder="Leave blank for no password"
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="off"
                />
              </Field>
              <Toggle
                label="Make public via Tailscale Funnel"
                checked={publicOn}
                onChange={setPublicOn}
              />
              <p className="field-hint">
                {publicOn
                  ? 'Anyone with the link can open it over the public internet. Turn on Funnel in the Network tab first (Public share links).'
                  : 'The link works only from your LAN or tailnet — not reachable from the public internet.'}
              </p>
              <div className="btn-row">
                <Btn variant="primary" busy={busy} onClick={create}>
                  Create share link
                </Btn>
              </div>
            </div>
          )}
          {created && (
            <div className="share-created">
              <div className="field-label group-label">Your share link</div>
              <div className="copy-row">
                <code className="copy-value">{shareUrl(created)}</code>
                <Btn variant="primary" onClick={() => copy(shareUrl(created))}>
                  {copyState === 'copied' ? 'Copied!' : 'Copy'}
                </Btn>
              </div>
              <p className="field-hint">
                Expires:{' '}
                {created.expires_at
                  ? new Date(created.expires_at * 1000).toLocaleString()
                  : 'never'}
                {created.has_password && ' · password-protected'}
                {created.public && ' · exposed to the public internet'}
              </p>
              <div className="btn-row">
                <Btn variant="ghost" onClick={() => setCreated(null)}>Create another</Btn>
                <Btn variant="danger-ghost" onClick={() => revoke(created.token)}>Revoke</Btn>
              </div>
            </div>
          )}

          {existing.length > 0 && (
            <div className="share-existing">
              <div className="field-label group-label">Active links for this item</div>
              <div className="share-list">
                {existing.map((s) => (
                  <div key={s.token} className="share-row">
                    <div className="share-row-main">
                      <div className="mono share-row-url">{shareUrl(s)}</div>
                      <div className="field-hint">
                        {s.expires_at
                          ? `expires ${new Date(s.expires_at * 1000).toLocaleString()}`
                          : 'never expires'}
                        {' · '}
                        {s.hits} hit{s.hits === 1 ? '' : 's'}
                        {s.public && ' · public'}
                        {s.has_password && ' · password'}
                      </div>
                    </div>
                    <div className="btn-row" style={{ marginTop: 0 }}>
                      <Btn variant="ghost" onClick={() => copy(shareUrl(s))}>Copy</Btn>
                      <Btn variant="danger-ghost" onClick={() => revoke(s.token)}>Revoke</Btn>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function FileTile({
  entry,
  sizeCell,
  onOpen,
  onShare,
  onDeleteRequest,
  onDeleteConfirm,
  onDeleteCancel,
  confirmingDelete,
}) {
  const showThumb = THUMB_KINDS.has(entry.kind)
  return (
    <div className={`tile tile-${entry.kind} ${confirmingDelete ? 'is-confirming' : ''}`}>
      <button className="tile-main" onClick={onOpen}>
        <div className="tile-thumb">
          {showThumb ? (
            <img
              src={THUMB(entry.path, 240)}
              alt=""
              loading="lazy"
              className="tile-img"
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
          ) : (
            <div className="tile-fallback">
              <FileIcon kind={entry.kind} />
            </div>
          )}
          {entry.kind === 'video' && (
            <div className="tile-badge">
              <Icon name="play" />
            </div>
          )}
        </div>
        <div className="tile-body">
          <div className={`tile-name mono ${entry.is_dir ? 'file-dir' : ''}`}>{entry.name}</div>
          <div className="tile-meta mono">{sizeCell}</div>
        </div>
      </button>
      <div className="tile-actions" onClick={(e) => e.stopPropagation()}>
        {confirmingDelete ? (
          <>
            <button className="tile-action danger" onClick={onDeleteConfirm} title="Confirm delete">
              <Icon name="check" />
            </button>
            <button className="tile-action" onClick={onDeleteCancel} title="Cancel">
              <Icon name="x" />
            </button>
          </>
        ) : (
          <>
            <button className="tile-action" onClick={onShare} title={`Share ${entry.name}`}>
              <Icon name="share" />
            </button>
            <a
              className="tile-action"
              href={DOWNLOAD(entry.path)}
              onClick={(e) => e.stopPropagation()}
              title={entry.is_dir ? 'Download folder as .zip' : 'Download'}
            >
              <Icon name="download" />
            </a>
            <button className="tile-action" onClick={onDeleteRequest} title={`Delete ${entry.name}`}>
              <Icon name="trash" />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

function FileIcon({ kind }) {
  if (kind === 'dir') {
    return (
      <svg className="file-glyph glyph-dir" viewBox="0 0 16 16" aria-hidden="true">
        <path
          d="M1.5 4.1a1 1 0 0 1 1-1h3.1l1.4 1.5h6.5a1 1 0 0 1 1 1v6.3a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1z"
          fill="currentColor"
          fillOpacity="0.16"
          stroke="currentColor"
          strokeWidth="1"
          strokeLinejoin="round"
        />
      </svg>
    )
  }
  return <span className={`file-glyph glyph-${kind}`}>{KIND_GLYPH[kind]}</span>
}

function fmtDate(mtime) {
  return new Date(mtime * 1000).toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const SLIDE_MS = 4000 // per-image dwell time in slideshow mode

function Preview({ items, initialIndex, onClose }) {
  const [index, setIndex] = useState(initialIndex)
  const [text, setText] = useState(null)
  const [error, setError] = useState('')
  const [volPct, setVolPct] = useState(null) // brief on-screen volume readout
  const [slideshow, setSlideshow] = useState(false)
  const [isFull, setIsFull] = useState(false)
  const mediaRef = useRef(null)
  const boxRef = useRef(null)
  const volumeRef = useRef(1)
  const volTimer = useRef(null)
  const slideTimer = useRef(null)

  const item = items[index]
  const many = items.length > 1
  const isPlayable = item.kind === 'video' || item.kind === 'audio'

  const go = useCallback(
    (delta) => setIndex((i) => (i + delta + items.length) % items.length),
    [items.length],
  )

  const setVolume = useCallback((v) => {
    const val = Math.max(0, Math.min(1, Math.round(v * 10) / 10))
    volumeRef.current = val
    if (mediaRef.current) mediaRef.current.volume = val
    setVolPct(Math.round(val * 100))
    clearTimeout(volTimer.current)
    volTimer.current = setTimeout(() => setVolPct(null), 900)
  }, [])

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) boxRef.current?.requestFullscreen?.()
    else document.exitFullscreen?.()
  }, [])

  // load text for text previews; reset per item
  useEffect(() => {
    setText(null)
    setError('')
    if (item.kind === 'text') {
      api(`/files/text?path=${encodeURIComponent(item.path)}`)
        .then((r) => setText(r.text))
        .catch((err) => setError(err.detail))
    }
  }, [item])

  // re-apply the persisted volume whenever a new media element mounts
  useEffect(() => {
    if (mediaRef.current) mediaRef.current.volume = volumeRef.current
  }, [index])

  // keep the fullscreen flag in sync (Esc/UI can exit it out from under us)
  useEffect(() => {
    const onFs = () => setIsFull(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', onFs)
    return () => document.removeEventListener('fullscreenchange', onFs)
  }, [])

  // slideshow: images/audio advance on a timer; videos advance when they end
  useEffect(() => {
    clearTimeout(slideTimer.current)
    if (!slideshow || !many || item.kind === 'video') return
    slideTimer.current = setTimeout(() => go(1), SLIDE_MS)
    return () => clearTimeout(slideTimer.current)
  }, [slideshow, index, item, many, go])

  useEffect(() => {
    function onKey(e) {
      switch (e.key) {
        case 'Escape':
          // let the browser exit fullscreen first; only close when windowed
          if (!document.fullscreenElement) onClose()
          break
        case 'ArrowRight':
          if (many) {
            e.preventDefault()
            go(1)
          }
          break
        case 'ArrowLeft':
          if (many) {
            e.preventDefault()
            go(-1)
          }
          break
        case ' ':
          if (isPlayable && mediaRef.current) {
            e.preventDefault()
            mediaRef.current.paused ? mediaRef.current.play() : mediaRef.current.pause()
          }
          break
        case 'ArrowUp':
          if (isPlayable && mediaRef.current) {
            e.preventDefault()
            setVolume(mediaRef.current.volume + 0.1)
          }
          break
        case 'ArrowDown':
          if (isPlayable && mediaRef.current) {
            e.preventDefault()
            setVolume(mediaRef.current.volume - 0.1)
          }
          break
        case 'f':
        case 'F':
          e.preventDefault()
          toggleFullscreen()
          break
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, isPlayable, many, onClose, setVolume, toggleFullscreen])

  return (
    <div className="preview-overlay" onClick={onClose}>
      <div className="preview-box" ref={boxRef} onClick={(e) => e.stopPropagation()}>
        <header className="preview-head">
          <span className="mono preview-name">
            {item.name}
            {many && <span className="preview-count"> · {index + 1} / {items.length}</span>}
          </span>
          <div className="btn-row" style={{ marginTop: 0 }}>
            {many && (
              <Btn variant={slideshow ? 'primary' : 'default'} onClick={() => setSlideshow((s) => !s)}>
                {slideshow ? '❚❚ Stop' : '▶ Slideshow'}
              </Btn>
            )}
            <Btn onClick={toggleFullscreen} title="Fullscreen (f)">
              {isFull ? '⤢ Exit' : '⛶ Fullscreen'}
            </Btn>
            <a className="btn" href={DOWNLOAD(item.path)}>
              <Icon name="download" /> Download
            </a>
            <Btn variant="ghost" onClick={onClose}>
              Close
            </Btn>
          </div>
        </header>

        <div className="preview-body">
          {many && (
            <button className="preview-nav prev" onClick={() => go(-1)} title="Previous (←)" aria-label="Previous">
              ‹
            </button>
          )}

          {item.kind === 'image' && <img src={RAW(item.path)} alt={item.name} className="preview-media" />}
          {item.kind === 'video' && (
            <video
              key={item.path}
              ref={mediaRef}
              src={RAW(item.path)}
              className="preview-media"
              controls
              autoPlay
              onEnded={() => slideshow && many && go(1)}
            />
          )}
          {item.kind === 'audio' && (
            <audio
              key={item.path}
              ref={mediaRef}
              src={RAW(item.path)}
              controls
              autoPlay
              className="preview-audio"
              onEnded={() => slideshow && many && go(1)}
            />
          )}
          {item.kind === 'text' &&
            (error ? (
              <div className="form-error">{error}</div>
            ) : text === null ? (
              <p className="field-hint">Loading…</p>
            ) : (
              <pre className="code-block preview-text">{text}</pre>
            ))}

          {many && (
            <button className="preview-nav next" onClick={() => go(1)} title="Next (→)" aria-label="Next">
              ›
            </button>
          )}

          {volPct !== null && <div className="preview-volume mono">Volume {volPct}%</div>}

          {slideshow && item.kind !== 'video' && (
            <div className="slide-progress">
              <div key={index} className="slide-progress-fill" style={{ animationDuration: `${SLIDE_MS}ms` }} />
            </div>
          )}
        </div>

        <footer className="preview-hint mono">
          {many && '← → switch · '}
          {isPlayable && 'space play/pause · ↑ ↓ volume · '}
          f fullscreen · esc close
        </footer>
      </div>
    </div>
  )
}

export default function FilesTab() {
  const [roots, setRoots] = useState(null)
  const [root, setRoot] = useState(null)
  const [path, setPath] = useState(null)
  const [listing, setListing] = useState(null)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [upProgress, setUpProgress] = useState(null) // {loaded, total, rate, files}
  const [view, setView] = useState(() => localStorage.getItem(VIEW_KEY) || 'list')
  const [newFolder, setNewFolder] = useState(false)
  const [folderName, setFolderName] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [shareFor, setShareFor] = useState(null)
  const fileInput = useRef(null)
  // recursive folder sizes, computed lazily and cached across navigation
  const sizeCache = useRef(new Map())
  const [, bumpSizes] = useState(0)
  const [sortKey, setSortKey] = useState('name') // 'name' | 'size' | 'modified'
  const [sortDir, setSortDir] = useState('asc') // 'asc' | 'desc'
  const [query, setQuery] = useState('')

  useEffect(() => {
    api('/files/roots')
      .then((r) => {
        setRoots(r.roots)
        if (r.roots.length) {
          setRoot(r.roots[0].path)
          setPath(r.roots[0].path)
        }
      })
      .catch((err) => setError(err.detail))
  }, [])

  useEffect(() => {
    if (!path) return
    let alive = true
    setError('')
    api(`/files/list?path=${encodeURIComponent(path)}`)
      .then((r) => alive && setListing(r))
      .catch((err) => alive && setError(err.detail))
    return () => {
      alive = false
    }
  }, [path])

  // After a listing arrives, compute folder sizes in the background so the
  // list itself stays instant. Cached per path, limited concurrency.
  useEffect(() => {
    if (!listing) return
    let cancelled = false
    const pending = listing.entries.filter((e) => e.is_dir && !sizeCache.current.has(e.path))
    if (!pending.length) return
    let next = 0
    async function worker() {
      while (!cancelled && next < pending.length) {
        const entry = pending[next++]
        sizeCache.current.set(entry.path, { pending: true })
        bumpSizes((v) => v + 1)
        try {
          const r = await api(`/files/dirsize?path=${encodeURIComponent(entry.path)}`)
          if (cancelled) return
          sizeCache.current.set(entry.path, { size: r.size, files: r.files })
        } catch {
          if (cancelled) return
          sizeCache.current.set(entry.path, { error: true })
        }
        bumpSizes((v) => v + 1)
      }
    }
    Promise.all([worker(), worker(), worker()])
    return () => {
      cancelled = true
    }
  }, [listing])

  function refresh() {
    if (path)
      api(`/files/list?path=${encodeURIComponent(path)}`)
        .then(setListing)
        .catch((err) => setError(err.detail))
  }

  function sizeOf(entry) {
    if (!entry.is_dir) return entry.size
    const s = sizeCache.current.get(entry.path)
    return s && typeof s.size === 'number' ? s.size : -1 // pending/unknown sorts first
  }

  function sizeCell(entry) {
    if (!entry.is_dir) return fmtBytes(entry.size)
    const s = sizeCache.current.get(entry.path)
    if (!s || s.pending) return <span className="tone-muted">…</span>
    if (s.error) return '—'
    return <span title={`${s.files} file${s.files === 1 ? '' : 's'}`}>{fmtBytes(s.size)}</span>
  }

  // Clicking a column sets it as the sort key; clicking the active one flips
  // direction. New columns default to the most useful direction.
  function toggleSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'name' ? 'asc' : 'desc')
    }
  }

  function sortArrow(key) {
    if (key !== sortKey) return ''
    return sortDir === 'asc' ? '▲' : '▼'
  }

  function setViewMode(v) {
    setView(v)
    try {
      localStorage.setItem(VIEW_KEY, v)
    } catch {
      /* private mode: ignore */
    }
  }

  function visibleEntries() {
    if (!listing) return []
    const q = query.trim().toLowerCase()
    const filtered = q ? listing.entries.filter((e) => e.name.toLowerCase().includes(q)) : listing.entries
    const dir = sortDir === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => {
      if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1 // folders always first
      let cmp
      if (sortKey === 'size') cmp = sizeOf(a) - sizeOf(b)
      else if (sortKey === 'modified') cmp = a.mtime - b.mtime
      else cmp = a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true })
      return cmp * dir
    })
  }

  function open(entry) {
    if (entry.is_dir) {
      setPath(entry.path)
    } else if (GALLERY_KINDS.includes(entry.kind)) {
      // arrow keys move through the photos/videos/audio in this folder
      const gallery = listing.entries.filter((e) => GALLERY_KINDS.includes(e.kind))
      const idx = gallery.findIndex((e) => e.path === entry.path)
      setPreview({ items: gallery, index: Math.max(0, idx) })
    } else if (entry.kind === 'text') {
      setPreview({ items: [entry], index: 0 })
    } else {
      window.location.href = DOWNLOAD(entry.path)
    }
  }

  function goUp() {
    if (path === root) return
    const parent = path.slice(0, path.lastIndexOf('/')) || '/'
    setPath(parent.startsWith(root) ? parent : root)
  }

  async function upload(files) {
    if (!files.length) return
    setUploading(true)
    // fetch doesn't emit upload progress in browsers; XHR does via
    // xhr.upload.onprogress, so we hand-roll the request.
    const form = new FormData()
    form.append('path', path)
    for (const f of files) form.append('files', f)
    const total = files.reduce((n, f) => n + f.size, 0)
    setUpProgress({ loaded: 0, total, rate: 0, files: files.length, done: 0 })

    try {
      const started = Date.now()
      const data = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('POST', '/api/files/upload', true)
        xhr.withCredentials = true
        xhr.upload.onprogress = (e) => {
          if (!e.lengthComputable) return
          const secs = Math.max(0.1, (Date.now() - started) / 1000)
          setUpProgress({
            loaded: e.loaded,
            total: e.total,
            rate: e.loaded / secs,
            files: files.length,
            done: Math.min(files.length, Math.round((e.loaded / e.total) * files.length)),
          })
        }
        xhr.onload = () => {
          let body = {}
          try { body = JSON.parse(xhr.responseText) } catch { /* not JSON */ }
          if (xhr.status >= 200 && xhr.status < 300) resolve(body)
          else reject(new Error(body.detail || `Upload failed (HTTP ${xhr.status})`))
        }
        xhr.onerror = () => reject(new Error('Network error during upload'))
        xhr.onabort = () => reject(new Error('Upload cancelled'))
        xhr.send(form)
      })
      toast.ok(data.message || `Uploaded ${files.length} file(s)`)
      refresh()
    } catch (err) {
      toast.err(err.message)
    } finally {
      setUploading(false)
      setUpProgress(null)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function createFolder() {
    try {
      const res = await api('/files/mkdir', { method: 'POST', body: { path, name: folderName.trim() } })
      toast.ok(res.message)
      setNewFolder(false)
      setFolderName('')
      refresh()
    } catch (err) {
      toast.err(err.detail)
    }
  }

  async function doDelete(entry) {
    try {
      await api('/files/delete', { method: 'POST', body: { path: entry.path } })
      toast.ok(`Deleted ${entry.name}`)
      sizeCache.current.delete(entry.path)
      setConfirmDelete(null)
      refresh()
    } catch (err) {
      toast.err(err.detail)
    }
  }

  if (roots && roots.length === 0) {
    return (
      <div className="stack">
        <Panel label="files" meta="nas">
          <EmptyState>
            No NAS location yet. Create a RAID array or add a Samba share on the Storage tab, then your files show up
            here.
          </EmptyState>
        </Panel>
      </div>
    )
  }

  // breadcrumb segments relative to the selected root
  const rel = path && root && path.length > root.length ? path.slice(root.length).split('/').filter(Boolean) : []
  const visible = visibleEntries()

  return (
    <div className="stack">
      <Panel
        label="files"
        meta="nas"
        actions={
          <>
            {roots && roots.length > 1 && (
              <select
                className="input"
                style={{ width: 'auto' }}
                value={root || ''}
                onChange={(e) => {
                  setRoot(e.target.value)
                  setPath(e.target.value)
                }}
              >
                {roots.map((r) => (
                  <option key={r.path} value={r.path}>
                    {r.label}
                  </option>
                ))}
              </select>
            )}
            <Btn onClick={() => setNewFolder((v) => !v)}>
              <Icon name="new-folder" /> New folder
            </Btn>
            <Btn variant="primary" onClick={() => fileInput.current?.click()} busy={uploading}>
              <Icon name="upload" /> Upload
            </Btn>
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              onChange={(e) => upload([...e.target.files])}
            />
          </>
        }
      >
        <div className="crumbs">
          <button className="crumb" onClick={() => setPath(root)}>
            {roots?.find((r) => r.path === root)?.label || 'root'}
          </button>
          {rel.map((seg, i) => {
            const target = root + '/' + rel.slice(0, i + 1).join('/')
            return (
              <span key={target} className="crumb-wrap">
                <span className="crumb-sep">/</span>
                <button className="crumb" onClick={() => setPath(target)}>
                  {seg}
                </button>
              </span>
            )
          })}
          {path !== root && (
            <button className="crumb-up" onClick={goUp} title="Up one folder">
              <Icon name="up" /> Up
            </button>
          )}
        </div>

        {newFolder && (
          <div className="confirm-box">
            <div className="btn-row" style={{ marginTop: 0 }}>
              <input
                className="input mono"
                placeholder="folder name"
                value={folderName}
                autoFocus
                onChange={(e) => setFolderName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && folderName.trim() && createFolder()}
                style={{ maxWidth: 260 }}
              />
              <Btn variant="primary" disabled={!folderName.trim()} onClick={createFolder}>
                Create
              </Btn>
              <Btn variant="ghost" onClick={() => setNewFolder(false)}>
                Cancel
              </Btn>
            </div>
          </div>
        )}

        {upProgress && (() => {
          const pct = upProgress.total ? (upProgress.loaded / upProgress.total) * 100 : 0
          return (
            <div className="upload-progress">
              <div className="upload-progress-head">
                <span className="mono upload-progress-title">
                  Uploading {upProgress.files} file{upProgress.files === 1 ? '' : 's'}
                </span>
                <span className="mono upload-progress-pct">{pct.toFixed(1)}%</span>
              </div>
              <div className="bar">
                <div className="bar-fill bar-accent" style={{ width: `${pct}%` }} />
              </div>
              <div className="upload-progress-meta mono">
                {fmtBytes(upProgress.loaded)} / {fmtBytes(upProgress.total)}
                {upProgress.rate > 0 && <> · {fmtBytes(upProgress.rate)}/s</>}
                {upProgress.rate > 0 && upProgress.loaded < upProgress.total && (
                  <> · {Math.max(1, Math.round((upProgress.total - upProgress.loaded) / upProgress.rate))} s left</>
                )}
              </div>
            </div>
          )
        })()}

        {listing && listing.entries.length > 0 && (
          <div className="files-toolbar">
            <input
              className="input mono files-search"
              placeholder="Filter by name…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query && (
              <span className="field-hint">
                {visible.length} of {listing.entries.length}
              </span>
            )}
            <div className="view-toggle" role="tablist" aria-label="View mode">
              <button
                className={`view-toggle-btn ${view === 'list' ? 'is-active' : ''}`}
                onClick={() => setViewMode('list')}
                title="List view"
                aria-pressed={view === 'list'}
              >
                <Icon name="list-view" />
              </button>
              <button
                className={`view-toggle-btn ${view === 'grid' ? 'is-active' : ''}`}
                onClick={() => setViewMode('grid')}
                title="Grid view"
                aria-pressed={view === 'grid'}
              >
                <Icon name="grid-view" />
              </button>
            </div>
          </div>
        )}

        {error && <div className="form-error">{error}</div>}

        {!listing && !error && <p className="field-hint">Reading folder…</p>}

        {listing && listing.entries.length === 0 && <EmptyState>This folder is empty.</EmptyState>}

        {listing && listing.entries.length > 0 && visible.length === 0 && (
          <EmptyState>No files match “{query}”.</EmptyState>
        )}

        {listing && visible.length > 0 && view === 'grid' && (
          <div className="files-grid">
            {visible.map((entry) => (
              <FileTile
                key={entry.path}
                entry={entry}
                sizeCell={
                  entry.is_dir
                    ? (() => {
                        const s = sizeCache.current.get(entry.path)
                        return s && typeof s.size === 'number' ? fmtBytes(s.size) : '…'
                      })()
                    : fmtBytes(entry.size)
                }
                onOpen={() => open(entry)}
                onShare={() => setShareFor(entry)}
                onDeleteRequest={() => setConfirmDelete(entry.path)}
                onDeleteConfirm={() => doDelete(entry)}
                onDeleteCancel={() => setConfirmDelete(null)}
                confirmingDelete={confirmDelete === entry.path}
              />
            ))}
          </div>
        )}

        {listing && visible.length > 0 && view === 'list' && (
          <div className="table-scroll">
            <table className="table files-table">
              <thead>
                <tr>
                  <th>
                    <button className="sort-th" onClick={() => toggleSort('name')}>
                      name <span className="sort-arrow">{sortArrow('name')}</span>
                    </button>
                  </th>
                  <th className="num">
                    <button className="sort-th sort-th-num" onClick={() => toggleSort('size')}>
                      <span className="sort-arrow">{sortArrow('size')}</span> size
                    </button>
                  </th>
                  <th>
                    <button className="sort-th" onClick={() => toggleSort('modified')}>
                      modified <span className="sort-arrow">{sortArrow('modified')}</span>
                    </button>
                  </th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((entry) => (
                  <tr key={entry.path} className="file-row">
                    <td>
                      <button className="file-name" onClick={() => open(entry)}>
                        <FileIcon kind={entry.kind} />
                        <span className={entry.is_dir ? 'file-dir' : ''}>{entry.name}</span>
                      </button>
                    </td>
                    <td className="num mono tone-muted">{sizeCell(entry)}</td>
                    <td className="mono tone-muted file-date">{fmtDate(entry.mtime)}</td>
                    <td className="file-actions">
                      <button
                        className="icon-btn"
                        onClick={() => setShareFor(entry)}
                        title={`Share ${entry.name}`}
                      >
                        <Icon name="share" />
                      </button>
                      <a
                        className="icon-btn"
                        href={DOWNLOAD(entry.path)}
                        title={entry.is_dir ? 'Download folder as .zip' : 'Download'}
                      >
                        <Icon name="download" />
                      </a>
                      {confirmDelete === entry.path ? (
                        <>
                          <button className="icon-btn danger" onClick={() => doDelete(entry)} title="Confirm delete">
                            <Icon name="check" />
                          </button>
                          <button className="icon-btn" onClick={() => setConfirmDelete(null)} title="Cancel">
                            <Icon name="x" />
                          </button>
                        </>
                      ) : (
                        <button
                          className="icon-btn"
                          onClick={() => setConfirmDelete(entry.path)}
                          title={`Delete ${entry.name}`}
                        >
                          <Icon name="trash" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {preview && (
        <Preview items={preview.items} initialIndex={preview.index} onClose={() => setPreview(null)} />
      )}
      {shareFor && <ShareDialog entry={shareFor} onClose={() => setShareFor(null)} />}
    </div>
  )
}
