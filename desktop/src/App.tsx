import { useEffect, useState } from "react";
import reactLogo from "./assets/react.svg";
import { invoke } from "@tauri-apps/api/core";
import "./App.css";

function App() {
  const [imagePath, setImagePath] = useState("");
  const [status, setStatus] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    if (!isRunning) return;
    const id = window.setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [isRunning]);

  async function runPipeline() {
    const trimmed = imagePath.trim();
    if (!trimmed) {
      setStatus("Please enter an image path before running.");
      return;
    }

    setIsRunning(true);
    setElapsedSec(0);
    setStatus("Running pipeline...");

    try {
      const result = await invoke<string>("run_pipeline", {
        imagePath: trimmed,
      });
      setStatus(`Success:\n${result}`);
    } catch (error) {
      setStatus(`Failed:\n${String(error)}`);
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="container">
      <h1>Multi-layered Wood Art Generator</h1>

      <label>
        Image path
        <input
          value={imagePath}
          onChange={(e) => setImagePath(e.currentTarget.value)}
          placeholder="/absolute/path/to/image.png"
          disabled={isRunning}
        />
      </label>

      <button onClick={runPipeline} disabled={isRunning}>
        {isRunning ? `Running...${elapsedSec}s` : "Run pipeline"}
      </button>

      {isRunning && <p>Working in background. The app is still responsive.</p>}
      <pre>{status}</pre>
    </main>
  );
}

export default App;
