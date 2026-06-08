import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";

export function useImagePath() {
  const [imagePath, setImagePath] = useState("");

  async function browseForImage() {
    const selected = await open({
      title: "Select a PNG image you want to turn into separate layers",
      multiple: false,
      filters: [{ name: "PNG Image", extensions: ["png"] }],
    });
    if (typeof selected === "string") {
      setImagePath(selected);
    }
  }

  return { imagePath, setImagePath, browseForImage };
}
