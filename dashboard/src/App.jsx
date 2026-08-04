import { useEffect, useState } from "react";
import { collection, onSnapshot, doc, updateDoc } from "firebase/firestore";
import { db } from "./firebase";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";

function App() {
  const [reports, setReports] = useState([]);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    const unsubscribe = onSnapshot(collection(db, "reports"), (snapshot) => {
      const data = snapshot.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      }));
      data.sort((a, b) => b.priority - a.priority);
      setReports(data);
    });
    return () => unsubscribe();
  }, []);

  const getPriorityStyle = (priority) => {
    if (priority >= 7) return { badge: "bg-red-100 text-red-700", border: "border-red-500" };
    if (priority >= 4) return { badge: "bg-orange-100 text-orange-700", border: "border-orange-500" };
    return { badge: "bg-green-100 text-green-700", border: "border-green-500" };
  };

  const getStatusStyle = (status) => {
    if (status === "resolved") return "bg-green-100 text-green-700";
    if (status === "in-progress") return "bg-blue-100 text-blue-700";
    return "bg-gray-100 text-gray-700";
  };

  const updateStatus = async (reportId, newStatus) => {
    const reportRef = doc(db, "reports", reportId);
    await updateDoc(reportRef, { status: newStatus });
  };

  const askQuestion = async () => {
    if (!query.trim()) return;
    setAsking(true);
    setAnswer("");
    try {
      const formData = new FormData();
      formData.append("question", query);
      const res = await fetch("http://127.0.0.1:8000/query", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setAnswer(data.answer);
    } catch (err) {
      setAnswer("Failed to get answer. Is the backend running?");
    } finally {
      setAsking(false);
    }
  };

  const filteredReports =
    filter === "all" ? reports : reports.filter((r) => r.status === filter);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-3xl"></span>
          <div>
            <h1 className="text-xl font-bold text-slate-800">PotHawk Dashboard</h1>
            <p className="text-sm text-slate-500">Municipality Road Damage Monitor</p>
          </div>
        </div>
        <div className="flex gap-4 text-sm">
          <div className="text-center">
            <p className="text-2xl font-bold text-slate-800">{reports.length}</p>
            <p className="text-slate-500">Total</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-red-600">
              {reports.filter((r) => r.priority >= 7).length}
            </p>
            <p className="text-slate-500">High Priority</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-green-600">
              {reports.filter((r) => r.status === "resolved").length}
            </p>
            <p className="text-slate-500">Resolved</p>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Map + Reports */}
        <div className="lg:col-span-2 space-y-6">
          {/* Map */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="h-80">
              <MapContainer center={[20.5937, 78.9629]} zoom={4} style={{ height: "100%", width: "100%" }}>
                <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                {reports.map((report) => (
                  <Marker key={report.id} position={[report.latitude, report.longitude]}>
                    <Popup>
                      <strong>{report.filename}</strong>
                      <br />
                      Priority: {report.priority}/10
                      <br />
                      Status: {report.status}
                    </Popup>
                  </Marker>
                ))}
              </MapContainer>
            </div>
          </div>

          {/* Filter tabs */}
          <div className="flex gap-2">
            {["all", "pending", "in-progress", "resolved"].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition ${
                  filter === f
                    ? "bg-slate-800 text-white"
                    : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100"
                }`}
              >
                {f}
              </button>
            ))}
          </div>

          {/* Report cards */}
          <div className="space-y-3">
            {filteredReports.map((report) => {
              const style = getPriorityStyle(report.priority);
              return (
                <div
                  key={report.id}
                  className={`bg-white rounded-xl shadow-sm border-l-4 ${style.border} border border-slate-200 p-4`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-medium text-slate-800 text-sm truncate max-w-xs">
                      {report.filename}
                    </h3>
                    <span className={`text-xs font-semibold px-2 py-1 rounded-full ${style.badge}`}>
                      Priority {report.priority}/10
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-3 text-xs text-slate-500 mb-3">
                    <span>📍 {report.latitude?.toFixed(4)}, {report.longitude?.toFixed(4)}</span>
                    <span>🔍 {report.detections_count} detection(s)</span>
                    <span className={`px-2 py-0.5 rounded-full ${getStatusStyle(report.status)}`}>
                      {report.status}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => updateStatus(report.id, "in-progress")}
                      className="text-xs px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 font-medium"
                    >
                      Mark In Progress
                    </button>
                    <button
                      onClick={() => updateStatus(report.id, "resolved")}
                      className="text-xs px-3 py-1.5 rounded-lg bg-green-50 text-green-700 hover:bg-green-100 font-medium"
                    >
                      Mark Resolved
                    </button>
                  </div>
                </div>
              );
            })}
            {filteredReports.length === 0 && (
              <div className="text-center py-10 text-slate-400 text-sm">No reports found</div>
            )}
          </div>
        </div>

        {/* Right: AI Query Panel */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 sticky top-6">
            <h2 className="font-semibold text-slate-800 mb-1">🤖 Ask PotHawk AI</h2>
            <p className="text-xs text-slate-500 mb-4">
              Ask questions about your reports in plain English
            </p>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Show me all high priority reports"
              className="w-full text-sm border border-slate-200 rounded-lg p-3 mb-3 focus:outline-none focus:ring-2 focus:ring-slate-300 resize-none"
              rows={3}
            />
            <button
              onClick={askQuestion}
              disabled={asking}
              className="w-full bg-slate-800 text-white text-sm font-medium py-2 rounded-lg hover:bg-slate-700 disabled:opacity-50"
            >
              {asking ? "Thinking..." : "Ask"}
            </button>
            {answer && (
              <div className="mt-4 bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm text-slate-700 whitespace-pre-wrap">
                {answer}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
