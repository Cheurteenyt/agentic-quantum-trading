export default function TerminalPage() {
  return (
    <div className="anim-fade-up" style={{ height: "100%", display: "flex", flexDirection: "column", padding: 16 }}>
      <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div className="card-header">
          <span className="card-title">WSL Terminal</span>
          <span className="badge badge-medium">ttyd :7681</span>
        </div>
        <div style={{ flex: 1, overflow: "hidden", background: "#080d18" }}>
          <iframe
            src="http://localhost:7681"
            style={{ width: "100%", height: "100%", border: "none" }}
            title="Terminal WSL"
          />
        </div>
      </div>
    </div>
  )
}
