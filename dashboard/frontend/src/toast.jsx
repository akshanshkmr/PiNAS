import { useEffect, useState } from 'react'

let nextId = 1

export function toast(kind, message) {
  window.dispatchEvent(new CustomEvent('app-toast', { detail: { id: nextId++, kind, message } }))
}
toast.ok = (m) => toast('ok', m)
toast.err = (m) => toast('err', m)

export function ToastHost() {
  const [items, setItems] = useState([])

  useEffect(() => {
    function onToast(e) {
      const item = e.detail
      setItems((cur) => [...cur, item])
      setTimeout(() => setItems((cur) => cur.filter((t) => t.id !== item.id)), 5000)
    }
    window.addEventListener('app-toast', onToast)
    return () => window.removeEventListener('app-toast', onToast)
  }, [])

  if (!items.length) return null
  return (
    <div className="toast-host" role="status">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          {t.message}
        </div>
      ))}
    </div>
  )
}
