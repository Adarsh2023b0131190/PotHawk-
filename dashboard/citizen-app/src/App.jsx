import { useState } from "react";

function App() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [location, setLocation] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileChange = (e) => {
    const selected = e.target.files[0];
    if (selected) {
      setFile(selected);
      setPreview(URL.createObjectURL(selected));
      setResult(null);
    }
  };

  const getLocation = () => {
    if (!navigator.geolocation) {
      setError("Geolocation not supported by your browser");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
        setError(null);
      },
      () => setError("Location access denied. Please allow location.")
    );
  };

  const handleSubmit = async () => {
    if (!file || !location) {
      setError("Please select a photo and allow location access.");
      return;
    }
    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("latitude", location.latitude);
    formData.append("longitude", location.longitude);

    try {
      const response = await fetch("https://pothawk.onrender.com/query", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError("Failed to submit report. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setLocation(null);
    setResult(null);
    setError(null);
  };

  const getPriorityColor = (priority) => {
    if (priority >= 7) return "text-red-600 bg-red-50 border-red-200";
    if (priority >= 4) return "text-orange-600 bg-orange-50 border-orange-200";
    return "text-green-600 bg-green-50 border-green-200";
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="text-5xl mb-2"></div>
          <h1 className="text-2xl font-bold text-slate-800">PotHawk</h1>
          <p className="text-slate-500 text-sm mt-1">Report a pothole in your area</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
          {!result ? (
            <>
              {/* Photo upload */}
              <label className="block mb-4">
                <span className="text-sm font-medium text-slate-700 mb-2 block">Photo</span>
                {preview ? (
                  <div className="relative">
                    <img
                      src={preview}
                      alt="preview"
                      className="w-full h-48 object-cover rounded-xl border border-slate-200"
                    />
                    <button
                      onClick={reset}
                      className="absolute top-2 right-2 bg-white/90 text-slate-600 text-xs px-2 py-1 rounded-lg shadow"
                    >
                      Change
                    </button>
                  </div>
                ) : (
                  <div className="border-2 border-dashed border-slate-300 rounded-xl h-48 flex flex-col items-center justify-center cursor-pointer hover:border-slate-400 transition">
                    <span className="text-3xl mb-2">📷</span>
                    <span className="text-sm text-slate-500">Tap to select a photo</span>
                  </div>
                )}
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleFileChange}
                  className="hidden"
                />
              </label>

              {/* Location */}
              <button
                onClick={getLocation}
                className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-medium mb-4 transition ${
                  location
                    ? "bg-green-50 text-green-700 border border-green-200"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                📍 {location ? "Location Captured" : "Get My Location"}
              </button>

              {error && (
                <p className="text-red-600 text-sm mb-4 bg-red-50 border border-red-200 rounded-lg p-2">
                  {error}
                </p>
              )}

              {/* Submit */}
              <button
                onClick={handleSubmit}
                disabled={loading}
                className="w-full bg-slate-800 text-white font-medium py-3 rounded-xl hover:bg-slate-700 disabled:opacity-50 transition"
              >
                {loading ? "Analyzing..." : "Submit Report"}
              </button>
            </>
          ) : (
            <div className="text-center">
              <div className="text-4xl mb-3">✅</div>
              <h2 className="text-lg font-semibold text-slate-800 mb-4">Report Submitted!</h2>

              <div className={`border rounded-xl p-4 mb-4 ${getPriorityColor(result.priority)}`}>
                <p className="text-3xl font-bold">{result.priority}/10</p>
                <p className="text-sm font-medium mt-1">Priority Score</p>
              </div>

              <div className="text-sm text-slate-500 space-y-1 mb-6">
                <p>{result.detections_count} pothole(s) detected</p>
                <p>Status: {result.status}</p>
              </div>

              <button
                onClick={reset}
                className="w-full bg-slate-800 text-white font-medium py-3 rounded-xl hover:bg-slate-700 transition"
              >
                Report Another
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;