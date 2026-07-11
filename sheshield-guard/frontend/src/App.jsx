import React, { useEffect, useRef, useState, useCallback } from 'react'
import L from 'leaflet'

const SIGNAL_LABELS = {
  proximity: 'Proximity', pursuit: 'Pursuit', motion_violence: 'Violent motion',
  fall: 'Fall', loitering: 'Loitering', violence_x3d: 'Violence (X3D)',
  interaction_posec3d: 'Interaction (PoseC3D)', anomaly_rtfm: 'Anomaly (RTFM)',
}
const KIND_LABELS = {
  harassment_suspected: 'Suspected harassment', violence: 'Violence',
  pursuit: 'Pursuit / stalking', fall: 'Person down', anomaly: 'Unusual activity',
}

// ---------- Camera tile: live MJPEG + signature per-signal threat meters ----------
function CameraTile({ cam, status }) {
  const st = status || cam
  const state = st.state || 'CLEAR'
  const signals = st.signals || {}
  const meters = Object.entries(signals).filter(([k]) => k !== 'persons')
  return (
    <div className={`tile tile--${state.toLowerCase()}`}>
      <div className="tile__head">
        <span className="tile__name">{cam.name}</span>
        <span className={`badge badge--${state.toLowerCase()}`}>{state}</span>
      </div>
      <div className="tile__video">
        {cam.live
          ? <img src={`/api/cameras/${cam.id}/stream`} alt={`Live: ${cam.name}`} />
          : <div className="tile__offline">Camera offline — check the source and restart it</div>}
        <div className="tile__hud mono">
          <span>{st.fps ? `${st.fps} fps` : '—'}</span>
          <span>{signals.persons ? `${signals.persons} in view` : 'no one in view'}</span>
          <span>score {typeof st.score === 'number' ? st.score.toFixed(2) : '0.00'}</span>
        </div>
      </div>
      <div className="tile__meters">
        {meters.map(([k, v]) => (
          <div className="meter" key={k} title={`${SIGNAL_LABELS[k] || k}: ${v}`}>
            <span className="meter__label">{SIGNAL_LABELS[k] || k}</span>
            <span className="meter__track"><span className="meter__fill" style={{ width: `${Math.round(v * 100)}%` }} /></span>
            <span className="meter__val mono">{v.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------- Incident card with the human-in-the-loop gate ----------
function IncidentCard({ inc, onAction }) {
  const [busy, setBusy] = useState(false)
  const act = async (verb) => {
    setBusy(true)
    const r = await fetch(`/api/incidents/${inc.id}/${verb}`, { method: 'POST' })
    const data = await r.json()
    onAction(inc.id, verb === 'confirm' ? 'confirmed' : 'dismissed', data.alerts)
    setBusy(false)
  }
  return (
    <div className={`incident incident--${inc.status}`}>
      <div className="incident__row">
        <span className="incident__kind">{KIND_LABELS[inc.kind] || inc.kind}</span>
        <span className="mono incident__time">{new Date(inc.created_at).toLocaleTimeString()}</span>
      </div>
      <div className="incident__meta mono">
        {inc.camera_name} · score {Number(inc.score).toFixed(2)}
        {inc.nearest_station && <> · nearest: {inc.nearest_station} ({inc.nearest_station_km} km)</>}
      </div>
      {inc.has_evidence && (
        <a className="incident__evidence" href={`/api/incidents/${inc.id}/evidence`} target="_blank" rel="noreferrer">
          View evidence clip (faces blurred)
        </a>
      )}
      {inc.status === 'pending_review' ? (
        <div className="incident__actions">
          <button className="btn btn--confirm" disabled={busy} onClick={() => act('confirm')}>
            Confirm &amp; alert station
          </button>
          <button className="btn btn--dismiss" disabled={busy} onClick={() => act('dismiss')}>
            Dismiss (false alarm)
          </button>
        </div>
      ) : (
        <div className={`incident__status mono`}>
          {inc.status === 'confirmed' ? 'Alerts sent — see audit log' : 'Dismissed'}
          {inc.alerts && inc.alerts.some(a => a.simulated) && ' · some channels simulated (no PSCA API exists)'}
        </div>
      )}
    </div>
  )
}

// ---------- Map: cameras + police stations ----------
function StationMap({ cameras, stations }) {
  const ref = useRef(null)
  const mapRef = useRef(null)
  useEffect(() => {
    if (!ref.current || mapRef.current) return
    const map = L.map(ref.current, { zoomControl: false }).setView([31.4204, 73.0836], 13)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
    mapRef.current = map
  }, [])
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const layer = L.layerGroup().addTo(map)
    stations.forEach(s => L.circleMarker([s.latitude, s.longitude], {
      radius: 6, color: '#5B8DEF', fillColor: '#5B8DEF', fillOpacity: 0.9,
    }).bindTooltip(`Police: ${s.name}`).addTo(layer))
    cameras.forEach(c => L.circleMarker([c.latitude, c.longitude], {
      radius: 7, color: '#1AAE6F', fillColor: '#1AAE6F', fillOpacity: 0.9,
    }).bindTooltip(`Camera: ${c.name}`).addTo(layer))
    return () => layer.remove()
  }, [cameras, stations])
  return <div ref={ref} className="map" role="img" aria-label="Map of cameras and police stations" />
}

// ---------- App ----------
export default function App() {
  const [cameras, setCameras] = useState([])
  const [statuses, setStatuses] = useState({})
  const [incidents, setIncidents] = useState([])
  const [stations, setStations] = useState([])
  const [wsOk, setWsOk] = useState(false)

  const load = useCallback(async () => {
    const [c, i, s] = await Promise.all([
      fetch('/api/cameras').then(r => r.json()),
      fetch('/api/incidents').then(r => r.json()),
      fetch('/api/stations').then(r => r.json()),
    ])
    setCameras(c); setIncidents(i); setStations(s)
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    let ws, retry
    const connect = () => {
      ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/events`)
      ws.onopen = () => setWsOk(true)
      ws.onclose = () => { setWsOk(false); retry = setTimeout(connect, 2000) }
      ws.onmessage = (e) => {
        const ev = JSON.parse(e.data)
        if (ev.type === 'camera_status') {
          setStatuses(p => ({ ...p, [ev.camera_id]: ev }))
        } else if (ev.type === 'incident') {
          setIncidents(p => [{ ...ev, has_evidence: true }, ...p])
        } else if (ev.type === 'incident_update') {
          setIncidents(p => p.map(i => i.id === ev.id ? { ...i, status: ev.status, alerts: ev.alerts } : i))
        }
      }
    }
    connect()
    return () => { clearTimeout(retry); ws && ws.close() }
  }, [])

  const onAction = (id, status, alerts) =>
    setIncidents(p => p.map(i => i.id === id ? { ...i, status, alerts } : i))

  const pending = incidents.filter(i => i.status === 'pending_review').length

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark" aria-hidden>◆</span>
          <span className="brand__name">SheShield<em>-Guard</em></span>
          <span className="brand__sub">Safety Operations Console · Faisalabad</span>
        </div>
        <div className="topbar__status mono">
          <span className={`dot ${wsOk ? 'dot--ok' : 'dot--bad'}`} />
          {wsOk ? 'live feed connected' : 'reconnecting…'}
          {pending > 0 && <span className="pendingpill">{pending} awaiting review</span>}
        </div>
      </header>

      <main className="layout">
        <section className="cams" aria-label="Camera grid">
          {cameras.length === 0 && (
            <div className="empty">No cameras yet. Run <code>python seed.py</code> in the backend, or add one via POST /api/cameras.</div>
          )}
          {cameras.map(c => <CameraTile key={c.id} cam={c} status={statuses[c.id]} />)}
        </section>

        <aside className="rail">
          <h2 className="rail__title">Incidents</h2>
          <p className="rail__note">Nothing is sent to any station until you confirm it. Confirming sends SMS + email to the nearest station's registered contacts and logs a simulated PSCA notification — Pakistan has no public police API; call 15 for real emergencies.</p>
          <div className="rail__list">
            {incidents.length === 0 && <div className="empty">No incidents. The feed is clear.</div>}
            {incidents.map(i => <IncidentCard key={i.id} inc={i} onAction={onAction} />)}
          </div>
          <h2 className="rail__title">Coverage map</h2>
          <StationMap cameras={cameras} stations={stations} />
        </aside>
      </main>
    </div>
  )
}
