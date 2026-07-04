import { useCallback, useEffect, useRef, useState } from 'react'
import { api, fmtBytes } from '../api'
import { toast } from '../toast'
import { Badge, Btn, EmptyState, Panel } from './ui'

const GALLERY_KINDS = ['image', 'video', 'audio']

const RAW = (p) => `/status/api/files/raw?path=${encodeURIComponent(p)}`
const DOWNLOAD = (p) => `/status/api/files/download?path=${encodeURIComponent(p)}`

const KIND_GLYPH = { dir: '▸', image: '▧', video: '▶', audio: '♪', text: '≡', file: '·' }

function fmtDate(mtime) {
  return new Date(mtime * 1000).toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function Preview({ items, initialIndex, onClose }) {
  const [index, setIndex] = useState(initialIndex)
  const [text, setText] = useState(null)
  const [error, setError] = useState('')
  const [volPct, setVolPct] = useState(null) // brief on-screen volume readout
  const mediaRef = useRef(null)
  const volumeRef = useRef(1)
  const volTimer = useRef(null)

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

  useEffect(() => {
    function onKey(e) {
      switch (e.key) {
        case 'Escape':
          onClose()
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
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, isPlayable, many, onClose, setVolume])

  return (
    <div className="preview-overlay" onClick={onClose}>
      <div className="preview-box" onClick={(e) => e.stopPropagation()}>
        <header className="preview-head">
          <span className="mono preview-name">
            {item.name}
            {many && <span className="preview-count"> · {index + 1} / {items.length}</span>}
          </span>
          <div className="btn-row" style={{ marginTop: 0 }}>
            <a className="btn" href={DOWNLOAD(item.path)}>
              Download
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
            <video key={item.path} ref={mediaRef} src={RAW(item.path)} className="preview-media" controls autoPlay />
          )}
          {item.kind === 'audio' && (
            <audio key={item.path} ref={mediaRef} src={RAW(item.path)} controls autoPlay className="preview-audio" />
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
        </div>

        <footer className="preview-hint mono">
          {many && '← → switch · '}
          {isPlayable && 'space play/pause · ↑ ↓ volume · '}
          esc close
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
  const [newFolder, setNewFolder] = useState(false)
  const [folderName, setFolderName] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const fileInput = useRef(null)

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

  function refresh() {
    setPath((p) => p) // no-op; use reload below
    if (path)
      api(`/files/list?path=${encodeURIComponent(path)}`)
        .then(setListing)
        .catch((err) => setError(err.detail))
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
    try {
      const form = new FormData()
      form.append('path', path)
      for (const f of files) form.append('files', f)
      const res = await fetch('/status/api/files/upload', {
        method: 'POST',
        credentials: 'same-origin',
        body: form,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      toast.ok(data.message)
      refresh()
    } catch (err) {
      toast.err(err.message)
    } finally {
      setUploading(false)
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
      const res = await api('/files/delete', { method: 'POST', body: { path: entry.path } })
      toast.ok(`Deleted ${entry.name}`)
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
            <Btn onClick={() => setNewFolder((v) => !v)}>New folder</Btn>
            <Btn variant="primary" onClick={() => fileInput.current?.click()} busy={uploading}>
              Upload
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
            <Btn variant="ghost" onClick={goUp} className="crumb-up">
              ↑ Up
            </Btn>
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

        {error && <div className="form-error">{error}</div>}

        {!listing && !error && <p className="field-hint">Reading folder…</p>}

        {listing && listing.entries.length === 0 && <EmptyState>This folder is empty.</EmptyState>}

        {listing && listing.entries.length > 0 && (
          <div className="table-scroll">
            <table className="table files-table">
              <thead>
                <tr>
                  <th>name</th>
                  <th className="num">size</th>
                  <th>modified</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {listing.entries.map((entry) => (
                  <tr key={entry.path} className="file-row">
                    <td>
                      <button className="file-name" onClick={() => open(entry)}>
                        <span className={`file-glyph glyph-${entry.kind}`}>{KIND_GLYPH[entry.kind]}</span>
                        <span className={entry.is_dir ? 'file-dir' : ''}>{entry.name}</span>
                      </button>
                    </td>
                    <td className="num mono tone-muted">{entry.is_dir ? '—' : fmtBytes(entry.size)}</td>
                    <td className="mono tone-muted file-date">{fmtDate(entry.mtime)}</td>
                    <td className="file-actions">
                      {!entry.is_dir && (
                        <a className="icon-btn" href={DOWNLOAD(entry.path)} title="Download">
                          ↓
                        </a>
                      )}
                      {confirmDelete === entry.path ? (
                        <>
                          <button className="icon-btn danger" onClick={() => doDelete(entry)} title="Confirm delete">
                            ✓
                          </button>
                          <button className="icon-btn" onClick={() => setConfirmDelete(null)} title="Cancel">
                            ✕
                          </button>
                        </>
                      ) : (
                        <button
                          className="icon-btn"
                          onClick={() => setConfirmDelete(entry.path)}
                          title={`Delete ${entry.name}`}
                        >
                          🗑
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
    </div>
  )
}
