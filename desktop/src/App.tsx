import { useState } from "react";
import reactLogo from "./assets/react.svg";
import { invoke } from "@tauri-apps/api/core";
import "./App.css";

function App() {
  const [imagePath, setImagePath] = useState("");
  const [status, setStatus] = useState("");

  async function runPipeline() {
    setStatus("Running pipeline...");
    try {
      const result = await invoke<string>("run_pipeline", {
        imagePath,
      });
      setStatus(`Success:\n${result}`);
    } catch (error) {
      setStatus(`Failed:\n${String(error)}`);
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
        />
      </label>

      <button onClick={runPipeline}>Run pipeline</button>

      <pre>{status}</pre>
    </main>
  );
}

export default App;
